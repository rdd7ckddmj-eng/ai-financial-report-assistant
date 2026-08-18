const SCHEMA_VERSION = 1;
const STATUS_VALUES = new Set(["unsearched", "collected", "decoy"]);
const OUTCOME_VALUES = new Set(["collected", "decoy"]);

const asText = (value, fallback = "", max = 180) => {
  if (typeof value !== "string") return fallback;
  const clean = value.trim();
  return clean ? clean.slice(0, max) : fallback;
};

const asList = (value) => (Array.isArray(value) ? value : []);

const asNumber = (value, fallback, min = 0, max = 100) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
};

const asObject = (value) => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value;
};

const add = (parent, tag, className, text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  parent.append(node);
  return node;
};

const makeId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `office-${Date.now()}-${Math.random().toString(16).slice(2, 12)}`;
};

const cleanLocation = (raw, index) => {
  const item = asObject(raw);
  const id = asText(item.id, `location-${index + 1}`, 80);
  const status = STATUS_VALUES.has(item.status) ? item.status : "unsearched";
  return {
    id,
    label: asText(item.label, `待搜查位置 ${index + 1}`, 100),
    x: asNumber(item.x, 10 + (index % 4) * 22, 2, 98),
    y: asNumber(item.y, 34 + Math.floor(index / 4) * 42, 7, 94),
    status,
  };
};

const cleanDocument = (raw, index) => {
  const item = asObject(raw);
  return {
    id: asText(item.document_id, `collected-${index + 1}`, 80),
    location: asText(item.location, "已搜查位置", 100),
    title: asText(item.title, `已封装材料 ${index + 1}`, 150),
    type: asText(item.document_type, "待深读材料", 100),
  };
};

export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".office-game");
  if (!root) return undefined;
  // Streamlit can mount the next render before it invokes the cleanup
  // returned by the previous render.  Tear down the previous scene now, but
  // keep every returned cleanup bound to its own controller.  A cleanup that
  // looks up ``root.__officeSearchCleanup`` later can otherwise abort the new
  // scene's listeners; the first scan works, while the newly revealed
  // keepsake button becomes visually present but inert.
  root.__officeSearchCleanup?.();
  root.__officeSearchCleanup = undefined;
  const payload = asObject(data);
  const state = asObject(payload.state);
  const questionId = asText(payload.question_id, "", 80);
  const revision = Math.max(0, Math.trunc(asNumber(payload.revision, 0, 0, 1e6)));
  const locations = asList(state.locations).slice(0, 12).map(cleanLocation);
  const legalLocationIds = new Set(locations.map((item) => item.id));
  const documents = asList(state.discovered_documents).slice(0, 12).map(cleanDocument);
  const count = Math.max(0, Math.trunc(asNumber(state.count, documents.length, 0, 99)));
  const requiredCount = Math.max(1, Math.trunc(asNumber(state.required_count, 6, 1, 12)));
  const searchComplete = Boolean(state.search_complete) && count >= requiredCount;
  const acknowledgedId = asText(state.acknowledged_command_id, "", 100);
  const npc = asObject(state.npc);
  const feedback = asObject(state.feedback);
  const reveal = asObject(state.reveal);
  const handoff = asObject(state.handoff);
  const keepsakeDiscovered = Boolean(state.keepsake_discovered);
  const incomingRevealOutcome = OUTCOME_VALUES.has(reveal.outcome)
    ? reveal.outcome
    : "";
  const revealToken = acknowledgedId || [
    asText(reveal.location_id, "", 80),
    incomingRevealOutcome,
    asText(reveal.title, "", 80),
  ].join(":");
  const shouldShowReveal = Boolean(
    incomingRevealOutcome &&
    revealToken &&
    root.dataset.shownRevealToken !== revealToken
  );
  const shell = document.createElement("section");
  shell.className = "office-shell";
  const controller = new AbortController();
  const { signal } = controller;
  let pendingLocationId = "";
  let pendingCommand = false;
  let selectedLocationId = "";
  let hintTimer = 0;
  let hintClearTimer = 0;
  let hintIndex = 0;

  const announce = document.createElement("div");
  announce.className = "office-a11y-status";
  announce.setAttribute("role", "status");
  announce.setAttribute("aria-live", "polite");

  const submit = (action, extra = {}) => {
    if (pendingCommand) return;
    pendingCommand = true;
    const command = {
      schema_version: SCHEMA_VERSION,
      command_id: makeId(),
      question_id: questionId,
      revision,
      action,
      ...extra,
    };
    announce.textContent = action === "finish_search"
      ? "正在封装现场材料"
      : action === "discover_keepsake"
        ? "正在封存隐蔽信物"
        : "正在核验搜查位置";
    finish.disabled = true;
    finish.setAttribute("aria-disabled", "true");
    setTriggerValue("command", command);
  };

  const hud = add(shell, "header", "office-hud");
  const brand = add(hud, "div", "office-brand");
  add(brand, "small", "", "FANGZHENG AI · CASE 01");
  add(brand, "strong", "", asText(state.scene_title, "失序办公室", 80));
  const mission = add(hud, "div", "office-mission");
  add(mission, "small", "", "04 · SPATIAL EVIDENCE SEARCH");
  add(
    mission,
    "strong",
    "",
    asText(state.objective, "在八个真实物件中找到六份材料；显眼不等于重要。", 180),
  );
  const progress = add(hud, "div", "office-progress");
  const meter = add(progress, "div", "office-progress-meter");
  const meterFill = add(meter, "span", "");
  meterFill.style.setProperty(
    "--office-progress",
    `${Math.min(100, (count / requiredCount) * 100)}%`,
  );
  add(progress, "strong", "", `${count} / ${requiredCount}`);
  const toolbar = add(hud, "nav", "office-toolbar");
  toolbar.setAttribute("aria-label", "案件操作");
  const toolbarSpecs = [
    ["go_back", "←", "上一步"],
    ["rename_player", "名", "修改代号"],
    ["restart_game", "↻", "重新开始"],
    ["exit_game", "⌂", "退出案件"],
  ];
  toolbarSpecs.forEach(([action, icon, label]) => {
    const button = add(toolbar, "button", "office-toolbar-button");
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.title = label;
    add(button, "b", "", icon);
    add(button, "span", "", label);
    button.addEventListener("click", () => submit(action), { signal });
  });
  const finish = add(hud, "button", "office-finish", "封装证物袋 →");
  finish.type = "button";
  finish.disabled = !searchComplete;
  finish.setAttribute("aria-disabled", String(!searchComplete));
  finish.addEventListener("click", () => submit("finish_search"), { signal });

  const sceneScroll = add(shell, "div", "office-scene-scroll");
  sceneScroll.setAttribute("aria-label", "可横向探索的失序办公室");
  sceneScroll.tabIndex = 0;
  const canvas = add(sceneScroll, "div", "office-scene-canvas");
  const image = add(canvas, "img", "office-scene-image");
  image.src = "/app/static/cash-game-office-search-bg-v2.png";
  image.alt = "夜间办公室调查现场，会议屏、茶台、打印机、文件柜、工作站与碎纸机分布其中";
  image.draggable = false;
  add(canvas, "div", "office-scene-vignette");

  const hotspotById = new Map();
  const searchLocation = (location) => {
    if (location.status !== "unsearched" || pendingLocationId) return;
    pendingLocationId = location.id;
    const hotspot = hotspotById.get(location.id);
    hotspot?.classList.add("is-pending");
    hotspot?.setAttribute("aria-busy", "true");
    submit("discover_location", { location_id: location.id });
  };

  locations.forEach((location, index) => {
    const hotspot = add(canvas, "button", "office-hotspot");
    hotspot.type = "button";
    hotspot.style.setProperty("--hotspot-x", `${location.x}%`);
    hotspot.style.setProperty("--hotspot-y", `${location.y}%`);
    hotspot.dataset.locationId = location.id;
    hotspot.dataset.status = location.status;
    hotspot.setAttribute("aria-label", `搜查：${location.label}`);
    hotspot.setAttribute("aria-pressed", String(location.status !== "unsearched"));
    hotspot.disabled = location.status === "collected";
    if (location.status === "decoy") hotspot.disabled = false;
    hotspotById.set(location.id, hotspot);
    const label = add(canvas, "span", "office-object-label", location.label);
    label.style.setProperty("--hotspot-x", `${location.x}%`);
    label.style.setProperty("--hotspot-y", `${location.y}%`);
    hotspot.addEventListener("click", () => {
      if (location.status === "decoy") {
        announce.textContent = `${location.label}已检查；它不能独立形成证据`;
        return;
      }
      searchLocation(location);
    }, { signal });
    hotspot.addEventListener("pointerdown", () => {
      selectedLocationId = location.id;
      hotspot.classList.add("is-selected");
    }, { signal });
    hotspot.addEventListener("pointerup", () => {
      hotspot.classList.remove("is-selected");
    }, { signal });
    hotspot.addEventListener("pointercancel", () => {
      hotspot.classList.remove("is-selected");
    }, { signal });
    hotspot.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        selectedLocationId = "";
        hotspot.classList.remove("is-selected");
      }
    }, { signal });
    if (index === 0 && location.status === "unsearched") {
      hotspot.setAttribute("aria-describedby", "office-keyboard-help");
    }

    if (
      location.id === "crystal_award" &&
      location.status === "decoy" &&
      !keepsakeDiscovered
    ) {
      const keepsake = add(canvas, "button", "office-keepsake-clue");
      keepsake.type = "button";
      keepsake.style.setProperty("--hotspot-x", `${location.x}%`);
      keepsake.style.setProperty("--hotspot-y", `${location.y}%`);
      keepsake.setAttribute("aria-label", "检查水晶奖杯底座的一道异常反光");
      keepsake.title = "这道反光的角度不太自然";
      add(keepsake, "span", "", "⌕");
      keepsake.addEventListener("click", () => submit("discover_keepsake"), { signal });
    }
  });

  const clearHint = () => {
    globalThis.clearTimeout(hintTimer);
    globalThis.clearTimeout(hintClearTimer);
    hotspotById.forEach((hotspot) => hotspot.classList.remove("is-hinted"));
  };
  const scheduleHint = () => {
    clearHint();
    hintTimer = globalThis.setTimeout(() => {
      const candidates = locations.filter((item) => item.status === "unsearched");
      if (!candidates.length) return;
      const candidate = candidates[hintIndex % candidates.length];
      hintIndex += 1;
      const target = hotspotById.get(candidate.id);
      target?.classList.add("is-hinted");
      announce.textContent = "现场光线扫过一片尚未检查的区域";
      hintClearTimer = globalThis.setTimeout(() => {
        target?.classList.remove("is-hinted");
        scheduleHint();
      }, 2400);
    }, 20000);
  };
  const resetHintClock = () => scheduleHint();
  sceneScroll.addEventListener("pointerdown", resetHintClock, { signal });
  sceneScroll.addEventListener("keydown", resetHintClock, { signal });
  scheduleHint();

  if (Object.keys(handoff).length) {
    const handoffCard = add(canvas, "aside", "office-handoff");
    add(handoffCard, "small", "", "SIGNED INVESTIGATION ORDERS");
    add(
      handoffCard,
      "strong",
      "",
      asText(handoff.title, "第3幕签发的调查令", 110),
    );
    add(
      handoffCard,
      "p",
      "",
      asText(handoff.body, "带着调查边界搜查；不要先拿材料、再编问题。", 220),
    );
    const orderList = add(handoffCard, "div", "office-handoff-orders");
    asList(handoff.orders).slice(0, 4).forEach((rawOrder, index) => {
      const order = asObject(rawOrder);
      const orderCard = add(orderList, "article", "office-handoff-order");
      add(
        orderCard,
        "small",
        "",
        asText(order.title, `调查令 ${index + 1}`, 70),
      );
      add(
        orderCard,
        "span",
        "",
        asText(order.objective, "等待现场材料", 100),
      );
    });
  }

  const keyboardHelp = add(canvas, "span", "office-a11y-status", "Tab切换物件，Enter或空格搜查，左右方向键平移现场。");
  keyboardHelp.id = "office-keyboard-help";
  sceneScroll.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      sceneScroll.scrollBy({
        left: event.key === "ArrowRight" ? 180 : -180,
        behavior: "smooth",
      });
    } else if (event.key === "Escape" && selectedLocationId) {
      hotspotById.get(selectedLocationId)?.classList.remove("is-selected");
      selectedLocationId = "";
    }
  }, { signal });

  const npcCard = add(canvas, "aside", "office-npc-card");
  const npcImage = add(npcCard, "img", "office-npc-image");
  npcImage.src = asText(
    npc.image_url,
    "/app/static/cash-game-mentor-04.png",
    300,
  );
  npcImage.alt = `${asText(npc.name, "叶观澜", 40)}，${asText(npc.role, "现场取证官", 70)}`;
  const npcCopy = add(npcCard, "div", "office-npc-copy");
  add(npcCopy, "small", "", asText(npc.role, "现场取证官", 70));
  add(npcCopy, "strong", "", asText(npc.name, "叶观澜", 40));
  add(
    npcCopy,
    "p",
    "",
    asText(npc.line, "别急着相信最显眼的材料。先问它来自谁、发生在何时。", 220),
  );

  if (Object.keys(feedback).length) {
    const feedbackBox = add(canvas, "aside", "office-feedback");
    feedbackBox.dataset.tone = asText(feedback.tone, "info", 20);
    add(feedbackBox, "small", "", "调查终端");
    add(feedbackBox, "strong", "", asText(feedback.title, "现场保持开放", 90));
    add(feedbackBox, "p", "", asText(feedback.message, "继续搜查尚未核验的位置。", 240));
  }

  const bag = add(shell, "aside", "office-evidence-bag");
  bag.setAttribute("aria-label", `证物袋，已封装${count}份材料`);
  const bagHeading = add(bag, "div", "office-bag-heading");
  add(bagHeading, "small", "", "EVIDENCE BAG");
  add(bagHeading, "strong", "", `已封装 ${count} / ${requiredCount}`);
  if (keepsakeDiscovered) {
    const keepsakeChip = add(bagHeading, "span", "office-keepsake-chip", "暗纹放大镜");
    keepsakeChip.setAttribute("aria-label", "隐藏信物：暗纹放大镜已收入物品栏");
  }
  const bagList = add(bag, "div", "office-bag-list");
  if (!documents.length) {
    add(bagList, "div", "office-bag-empty", "证物袋为空｜从真实物件开始搜查");
  } else {
    documents.forEach((document) => {
      const card = add(bagList, "article", "office-bag-item");
      card.dataset.documentId = document.id;
      add(card, "small", "", document.location);
      add(card, "strong", "", document.title);
      add(card, "small", "", document.type);
    });
  }

  const closeReveal = () => {
    shell.querySelector(".office-reveal-backdrop")?.remove();
  };

  if (
    shouldShowReveal &&
    legalLocationIds.has(asText(reveal.location_id, "", 80))
  ) {
    const backdrop = add(shell, "div", "office-reveal-backdrop");
    const card = add(backdrop, "article", "office-reveal-card");
    card.dataset.outcome = incomingRevealOutcome;
    add(
      card,
      "small",
      "",
      incomingRevealOutcome === "collected" ? "FILE RECOVERED" : "HIGH-QUALITY DECOY",
    );
    add(
      card,
      "h2",
      "",
      asText(
        reveal.title,
        incomingRevealOutcome === "collected" ? "材料已进入证物袋" : "它很正式，但证明力不足",
        150,
      ),
    );
    add(
      card,
      "p",
      "",
      asText(
        reveal.message,
        incomingRevealOutcome === "collected"
          ? "先封装，不急着下结论；下一幕再逐页深读。"
          : "外观、语气和位置只能吸引注意，不能替代日期、签章和来源。",
        300,
      ),
    );
    const close = add(card, "button", "office-reveal-close", "继续搜查");
    close.type = "button";
    close.addEventListener("click", closeReveal, { signal });
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) closeReveal();
    }, { signal });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeReveal();
    }, { signal });
    queueMicrotask(() => close.focus());
    root.dataset.shownRevealToken = revealToken;
  }

  if (acknowledgedId) pendingLocationId = "";
  shell.append(announce);
  root.replaceChildren(shell);

  const cleanup = () => {
    clearHint();
    controller.abort();
  };
  root.__officeSearchCleanup = cleanup;

  if (sceneScroll.scrollWidth > sceneScroll.clientWidth) {
    const firstUnsearched = locations.find((item) => item.status === "unsearched");
    if (firstUnsearched) {
      const target = hotspotById.get(firstUnsearched.id);
      if (target) {
        requestAnimationFrame(() => {
          sceneScroll.scrollLeft = Math.max(0, target.offsetLeft - sceneScroll.clientWidth * 0.45);
        });
      }
    }
  }

  return () => {
    cleanup();
    if (root.__officeSearchCleanup === cleanup) {
      root.__officeSearchCleanup = undefined;
    }
  };
}
