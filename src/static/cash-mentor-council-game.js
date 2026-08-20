const SCHEMA_VERSION = 1;
const KEEPSAKE_STATUSES = new Set(["available", "matched"]);
const FEEDBACK_TONES = new Set(["neutral", "info", "success", "warning", "error"]);

const asObject = (value) => (
  value && typeof value === "object" && !Array.isArray(value) ? value : {}
);
const asList = (value) => (Array.isArray(value) ? value : []);
const asText = (value, fallback = "", max = 180) => {
  if (typeof value !== "string") return fallback;
  const cleaned = value.trim();
  return cleaned ? cleaned.slice(0, max) : fallback;
};
const asInteger = (value, fallback = 0, min = 0, max = 999) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.max(min, Math.min(max, Math.trunc(number)));
};
const add = (parent, tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  parent.append(node);
  return node;
};
const makeCommandId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `council-${Date.now()}-${Math.random().toString(16).slice(2, 12)}`;
};

const cleanKeepsake = (raw, index) => {
  const item = asObject(raw);
  const keepsakeId = asText(item.keepsake_id, `keepsake-${index + 1}`, 80);
  return {
    id: keepsakeId,
    name: asText(item.name ?? item.keepsake_name, `未命名信物 ${index + 1}`, 70),
    mark: asText(item.mark ?? item.keepsake_mark, "◇", 4),
    status: KEEPSAKE_STATUSES.has(item.status) ? item.status : "available",
  };
};

const cleanMentor = (raw, index) => {
  const item = asObject(raw);
  const matchedKeepsake = asObject(item.matched_keepsake);
  const matched = Boolean(item.matched);
  return {
    id: asText(item.mentor_id, `mentor-${index + 1}`, 80),
    step: asInteger(item.step, index + 1, 1, 99),
    name: asText(item.name, `第 ${index + 1} 席`, 40),
    role: asText(item.role, "联合复核席", 70),
    capability: asText(item.capability, "等待复核", 90),
    imageUrl: asText(item.image_url, `/app/static/cash-game-mentor-${String(index + 1).padStart(2, "0")}.png`, 260),
    matched,
    matchedKeepsake: matched ? {
      id: asText(matchedKeepsake.keepsake_id, "", 80),
      name: asText(matchedKeepsake.name ?? matchedKeepsake.keepsake_name, "已归还信物", 70),
      mark: asText(matchedKeepsake.mark ?? matchedKeepsake.keepsake_mark, "◆", 4),
    } : null,
    hint: matched ? asText(item.revealed_hint ?? item.council_hint, "这一席的复核方法已经解锁。", 280) : "",
  };
};

const cleanCounts = (raw, keepsakes, mentors) => {
  const counts = asObject(raw);
  return {
    discovered: asInteger(counts.discovered, keepsakes.length, 0, 99),
    matched: asInteger(
      counts.matched,
      mentors.filter((mentor) => mentor.matched).length,
      0,
      99,
    ),
  };
};

export default function renderMentorCouncil(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".mentor-council-game");
  if (!root) return undefined;

  root.__mentorCouncilCleanup?.();
  root.__mentorCouncilCleanup = undefined;

  const payload = asObject(data);
  const state = asObject(payload.state);
  const taskId = asText(payload.task_id, "", 120);
  const revision = asInteger(payload.revision, 0, 0, 1_000_000);
  const mentors = asList(state.mentors).slice(0, 12).map(cleanMentor);
  const mentorIds = new Set(mentors.map((mentor) => mentor.id));
  const keepsakes = asList(state.keepsakes).slice(0, 12).map(cleanKeepsake);
  const keepsakeById = new Map(keepsakes.map((item) => [item.id, item]));
  const counts = cleanCounts(state.counts, keepsakes, mentors);
  const feedback = asObject(state.feedback);
  const feedbackTone = FEEDBACK_TONES.has(feedback.tone)
    ? feedback.tone
    : "neutral";
  const rejectedKeepsakeId = asText(feedback.rejected_keepsake_id, "", 80);
  const canContinue = state.can_continue !== false;
  const acknowledgedId = asText(state.acknowledged_command_id, "", 128);

  const controller = new AbortController();
  const { signal } = controller;
  let selectedKeepsakeId = "";
  let pendingCommand = false;
  let pointer = null;
  let dragGhost = null;
  let suppressClickUntil = 0;

  const shell = document.createElement("section");
  shell.className = "council-shell";
  shell.dataset.feedbackTone = feedbackTone;
  const announce = add(shell, "div", "council-a11y-status");
  announce.setAttribute("role", "status");
  announce.setAttribute("aria-live", "polite");

  const submit = (action, extra = {}) => {
    if (pendingCommand || !taskId) return;
    pendingCommand = true;
    shell.classList.add("is-pending");
    announce.textContent = action === "submit_match"
      ? "正在请九席核验信物归属"
      : action === "continue_investigation"
        ? "正在签发真实历史调查委托"
        : "正在处理会场操作";
    setTriggerValue("command", {
      schema_version: SCHEMA_VERSION,
      command_id: makeCommandId(),
      task_id: taskId,
      revision,
      action,
      ...extra,
    });
  };

  const hud = add(shell, "header", "council-hud");
  const brand = add(hud, "div", "council-brand");
  add(brand, "small", "", "FANGZHENG AI · FINAL COUNCIL");
  add(
    brand,
    "strong",
    "",
    asText(state.title, "九席联合复核会", 90),
  );
  const mission = add(hud, "div", "council-mission");
  add(mission, "small", "", `调查员 · ${asText(state.player_name, "见习研究员", 40)}`);
  add(
    mission,
    "strong",
    "",
    asText(state.subtitle, "把信物交还给主人；提示只改变视角，不替你回答。", 170),
  );
  const progress = add(hud, "div", "council-progress");
  add(progress, "small", "", "COUNCIL RECORD");
  add(progress, "strong", "", `${counts.matched} / ${counts.discovered}`);
  add(progress, "span", "", "已解锁 / 已发现");
  const toolbar = add(hud, "nav", "council-toolbar");
  toolbar.setAttribute("aria-label", "联合复核会操作");
  [
    ["go_back", "←", "上一步"],
    ["rename_player", "名", "修改代号"],
    ["restart_game", "↻", "重新开始"],
    ["exit_game", "⌂", "退出案件"],
  ].forEach(([action, icon, label]) => {
    const button = add(toolbar, "button", "council-toolbar-button");
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    add(button, "b", "", icon);
    add(button, "span", "", label);
    button.addEventListener("click", () => submit(action), { signal });
  });

  const body = add(shell, "main", "council-body");
  const chamber = add(body, "section", "council-chamber");
  const chamberHeading = add(chamber, "div", "council-chamber-heading");
  const headingCopy = add(chamberHeading, "div", "");
  add(headingCopy, "small", "", "NINE DISCIPLINES · ONE EVIDENCE BOUNDARY");
  add(headingCopy, "h1", "", "让物件找到主人，让方法回到证据");
  add(chamberHeading, "span", "", "拖拽 · 点选 · Tab + Enter");
  const mentorViewport = add(chamber, "div", "council-mentor-viewport");
  mentorViewport.tabIndex = 0;
  mentorViewport.setAttribute("aria-label", "九席角色会场，可在内部滚动");
  const mentorGrid = add(mentorViewport, "div", "council-mentor-grid");
  const councilTable = add(mentorGrid, "section", "council-center-table");
  councilTable.setAttribute("aria-hidden", "true");
  add(councilTable, "small", "", "CENTRAL REVIEW DESK");
  add(councilTable, "strong", "", "九席不会替你判断，只会追问你的证据边界");
  const tableSelection = add(councilTable, "div", "council-table-selection");
  const tableMark = add(tableSelection, "b", "", "◇");
  const tableCopy = add(tableSelection, "span", "", "从下方信物栏拿起一件物品");
  add(councilTable, "p", "", "把物件拖进某一席，或先点物件再点角色。错配只会退回当前物件。 ");

  const mentorNodes = new Map();
  mentors.forEach((mentor) => {
    const card = add(mentorGrid, "button", "council-mentor");
    card.type = "button";
    card.dataset.mentorId = mentor.id;
    card.dataset.seatStep = String(mentor.step);
    card.dataset.matched = String(mentor.matched);
    card.setAttribute("aria-label", `${mentor.name}，${mentor.role}${mentor.matched ? "，信物已归还" : "，等待信物"}`);
    card.setAttribute("aria-pressed", String(mentor.matched));
    const portrait = add(card, "span", "council-mentor-portrait");
    const image = add(portrait, "img", "");
    image.src = mentor.imageUrl;
    image.alt = "";
    image.draggable = false;
    add(portrait, "i", "", String(mentor.step).padStart(2, "0"));
    const copy = add(card, "span", "council-mentor-copy");
    add(copy, "small", "", mentor.role);
    add(copy, "strong", "", mentor.name);
    add(copy, "span", "", mentor.capability);
    if (mentor.matched && mentor.matchedKeepsake) {
      const seal = add(card, "span", "council-match-seal");
      add(seal, "b", "", mentor.matchedKeepsake.mark);
      add(seal, "span", "", mentor.matchedKeepsake.name);
    } else {
      add(card, "span", "council-drop-copy", "将信物交给此席");
    }
    mentorNodes.set(mentor.id, card);
  });

  const side = add(body, "aside", "council-side");
  const feedbackCard = add(side, "section", "council-feedback");
  feedbackCard.dataset.tone = feedbackTone;
  add(feedbackCard, "small", "", "九席回执");
  add(
    feedbackCard,
    "strong",
    "",
    asText(feedback.title, "会场等待你的第一次交付", 100),
  );
  add(
    feedbackCard,
    "p",
    "",
    asText(
      feedback.message,
      "别按人物气场猜。先理解信物的用途，再判断它属于哪一种研究能力。",
      280,
    ),
  );
  const hintArchive = add(side, "section", "council-hint-archive");
  const hintHeading = add(hintArchive, "div", "council-hint-heading");
  add(hintHeading, "small", "", "METHOD ARCHIVE");
  add(hintHeading, "strong", "", "已解锁的思考方法");
  const hints = mentors.filter((mentor) => mentor.matched && mentor.hint);
  if (!hints.length) {
    add(hintArchive, "p", "council-hint-empty", "这里不会提前给答案。正确归还信物后，对应席位才会留下方法。");
  } else {
    const hintList = add(hintArchive, "div", "council-hint-list");
    hints.forEach((mentor) => {
      const hint = add(hintList, "article", "council-hint");
      const meta = add(hint, "div", "");
      add(meta, "b", "", mentor.name);
      add(meta, "small", "", mentor.role);
      add(hint, "p", "", mentor.hint);
    });
  }

  const inventory = add(shell, "footer", "council-inventory");
  const inventoryHeading = add(inventory, "div", "council-inventory-heading");
  add(inventoryHeading, "small", "", "DISCOVERED KEEPSAKES");
  add(inventoryHeading, "strong", "", keepsakes.length ? "信物栏" : "信物栏为空");
  add(
    inventoryHeading,
    "span",
    "",
    keepsakes.length
      ? "点选一件，再点角色；或直接拖到角色席位。"
      : "没有信物也能继续。过关与看见全部细节不是同一件事。",
  );
  const keepsakeViewport = add(inventory, "div", "council-keepsake-viewport");
  const keepsakeRack = add(keepsakeViewport, "div", "council-keepsake-rack");
  const keepsakeNodes = new Map();

  const updateSelection = () => {
    keepsakeNodes.forEach((node, keepsakeId) => {
      const selected = keepsakeId === selectedKeepsakeId;
      node.classList.toggle("is-selected", selected);
      node.setAttribute("aria-pressed", String(selected));
    });
    mentorNodes.forEach((node) => {
      node.classList.toggle("is-ready", Boolean(selectedKeepsakeId));
    });
    const selected = keepsakeById.get(selectedKeepsakeId);
    tableMark.textContent = selected?.mark || "◇";
    tableCopy.textContent = selected
      ? `手中信物｜${selected.name}`
      : "从下方信物栏拿起一件物品";
    announce.textContent = selected
      ? `已拿起${selected.name}；请选择一位角色交付`
      : "已放回信物栏";
  };

  const selectKeepsake = (keepsakeId) => {
    const item = keepsakeById.get(keepsakeId);
    if (!item || item.status !== "available") return;
    selectedKeepsakeId = selectedKeepsakeId === keepsakeId ? "" : keepsakeId;
    updateSelection();
  };

  const submitMatch = (mentorId, keepsakeId = selectedKeepsakeId) => {
    const item = keepsakeById.get(keepsakeId);
    if (!mentorIds.has(mentorId) || !item || item.status !== "available") {
      announce.textContent = "请先从信物栏选择一件尚未归还的信物";
      return;
    }
    const mentor = mentors.find((candidate) => candidate.id === mentorId);
    if (mentor?.matched) {
      announce.textContent = `${mentor.name}的席位已经完成交付`;
      return;
    }
    keepsakeNodes.get(keepsakeId)?.classList.add("is-pending");
    mentorNodes.get(mentorId)?.classList.add("is-pending");
    submit("submit_match", {
      keepsake_id: keepsakeId,
      mentor_id: mentorId,
    });
  };

  if (!keepsakes.length) {
    const empty = add(keepsakeRack, "div", "council-keepsake-empty");
    add(empty, "b", "", "没有找到信物，不等于不能形成判断。");
    add(empty, "span", "", "九席允许你不使用任何提示，直接进入真实历史调查。");
  } else {
    keepsakes.forEach((keepsake) => {
      const item = add(keepsakeRack, "button", "council-keepsake");
      item.type = "button";
      item.dataset.keepsakeId = keepsake.id;
      item.dataset.status = keepsake.status;
      item.disabled = keepsake.status === "matched";
      item.setAttribute("aria-pressed", "false");
      item.setAttribute("aria-label", `${keepsake.name}${keepsake.status === "matched" ? "，已归还" : "，可交付"}`);
      add(item, "b", "", keepsake.mark);
      const copy = add(item, "span", "");
      add(copy, "strong", "", keepsake.name);
      add(copy, "small", "", keepsake.status === "matched" ? "已归还并锁定" : "等待找到主人");
      if (keepsake.id === rejectedKeepsakeId) item.classList.add("is-rejected");
      keepsakeNodes.set(keepsake.id, item);
      item.addEventListener("click", () => {
        if (performance.now() < suppressClickUntil) return;
        selectKeepsake(keepsake.id);
      }, { signal });
      item.addEventListener("pointerdown", (event) => {
        if (keepsake.status !== "available" || event.button > 0) return;
        pointer = {
          id: event.pointerId,
          keepsakeId: keepsake.id,
          startX: event.clientX,
          startY: event.clientY,
          x: event.clientX,
          y: event.clientY,
          moved: false,
        };
        item.setPointerCapture?.(event.pointerId);
      }, { signal });
    });
  }

  mentorNodes.forEach((node, mentorId) => {
    node.addEventListener("click", () => submitMatch(mentorId), { signal });
    node.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && selectedKeepsakeId) {
        event.preventDefault();
        submitMatch(mentorId);
      }
    }, { signal });
  });

  const movePointer = (event) => {
    if (!pointer || event.pointerId !== pointer.id) return;
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    if (!pointer.moved) {
      pointer.moved = Math.hypot(
        pointer.x - pointer.startX,
        pointer.y - pointer.startY,
      ) > 7;
      if (pointer.moved) {
        selectedKeepsakeId = pointer.keepsakeId;
        updateSelection();
      }
    }
    if (!pointer.moved) return;
    event.preventDefault();
    if (!dragGhost) {
      const item = keepsakeById.get(pointer.keepsakeId);
      // Keep the ghost inside the component shadow tree so component-scoped
      // styles also apply in Streamlit's v2 renderer.
      dragGhost = add(shell, "div", "council-drag-ghost");
      add(dragGhost, "b", "", item?.mark || "◇");
      add(dragGhost, "span", "", item?.name || "信物");
    }
    dragGhost.style.left = `${pointer.x}px`;
    dragGhost.style.top = `${pointer.y}px`;
  };

  const endPointer = (event) => {
    if (!pointer || event.pointerId !== pointer.id) return;
    const activePointer = pointer;
    pointer = null;
    dragGhost?.remove();
    dragGhost = null;
    keepsakeNodes.get(activePointer.keepsakeId)?.releasePointerCapture?.(event.pointerId);
    if (!activePointer.moved) return;
    suppressClickUntil = performance.now() + 450;
    const hitRoot = root.getRootNode();
    const hitNode = hitRoot.elementFromPoint?.(event.clientX, event.clientY)
      || document.elementFromPoint(event.clientX, event.clientY);
    const target = hitNode?.closest?.("[data-mentor-id]");
    const mentorId = asText(target?.dataset?.mentorId, "", 80);
    if (mentorId) submitMatch(mentorId, activePointer.keepsakeId);
    else announce.textContent = "信物已回到栏中；拖到角色卡片以内才会提交";
  };
  document.addEventListener("pointermove", movePointer, { signal, passive: false });
  document.addEventListener("pointerup", endPointer, { signal });
  document.addEventListener("pointercancel", endPointer, { signal });
  shell.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && selectedKeepsakeId) {
      selectedKeepsakeId = "";
      updateSelection();
    }
  }, { signal });

  const continueButton = add(inventory, "button", "council-continue", "接受真实历史调查 →");
  continueButton.type = "button";
  continueButton.disabled = !canContinue;
  continueButton.setAttribute("aria-disabled", String(!canContinue));
  continueButton.addEventListener("click", () => submit("continue_investigation"), { signal });

  if (acknowledgedId) shell.dataset.acknowledgedCommandId = acknowledgedId;
  shell.append(announce);
  root.replaceChildren(shell);

  const cleanup = () => {
    dragGhost?.remove();
    dragGhost = null;
    controller.abort();
  };
  root.__mentorCouncilCleanup = cleanup;
  return () => {
    cleanup();
    if (root.__mentorCouncilCleanup === cleanup) {
      root.__mentorCouncilCleanup = undefined;
    }
  };
}
