const PHASES = ["routes", "hypothesis", "orders", "door"];
const SCHEMA_VERSION = 1;
const MAX_TEXT = 240;
const MAX_DRAFT_PLACEMENTS = 6;

const asText = (value, fallback = "", limit = MAX_TEXT) => {
  if (typeof value !== "string" && typeof value !== "number") return fallback;
  const result = String(value).trim().slice(0, limit);
  return result || fallback;
};

const asObject = (value) => (
  value && typeof value === "object" && !Array.isArray(value) ? value : {}
);

const asList = (value) => (
  Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : []
);

const makeId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const add = (parent, tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = asText(text, "", 2000);
  parent.appendChild(node);
  return node;
};

const normaliseItem = (raw, index, prefix) => {
  const item = asObject(raw);
  const id = asText(item.id, `${prefix}-${index + 1}`, 80);
  return {
    id,
    title: asText(item.title, `材料 ${index + 1}`, 100),
    body: asText(item.body, "", 280),
    eyebrow: asText(item.eyebrow, "待处理", 60),
    hint: asText(item.hint, "", 180),
    label: asText(item.label, item.title || `材料 ${index + 1}`, 100),
  };
};

const cleanPlacementMap = (raw, legalItems, legalTargets) => {
  const source = asObject(raw);
  const result = {};
  for (const [itemId, targetId] of Object.entries(source)) {
    if (Object.keys(result).length >= MAX_DRAFT_PLACEMENTS) break;
    if (
      legalItems.has(itemId) && legalTargets.has(targetId) &&
      typeof targetId === "string"
    ) {
      result[itemId] = targetId;
    }
  }
  return result;
};

const phaseCollection = (state, phase) => {
  if (phase === "routes") {
    return {
      items: asList(state.cards).map((item, index) => normaliseItem(item, index, "fact")),
      targets: asList(state.zones).map((item, index) => normaliseItem(item, index, "zone")),
    };
  }
  if (phase === "hypothesis") {
    return {
      items: [normaliseItem(state.gap_token || {}, 0, "gap")],
      targets: asList(state.hypothesis_slots).map(
        (item, index) => normaliseItem(item, index, "hypothesis")
      ),
    };
  }
  if (phase === "orders") {
    return {
      items: asList(state.materials).map((item, index) => normaliseItem(item, index, "material")),
      targets: asList(state.evidence_pockets).map(
        (item, index) => normaliseItem(item, index, "pocket")
      ),
    };
  }
  return {
    items: [normaliseItem(state.issued_order || {}, 0, "order")],
    targets: [normaliseItem(state.door || {}, 0, "door")],
  };
};

const readDraft = (storageKey, questionId, revision, phase, legalItems, legalTargets) => {
  const empty = { placements: {}, appliedAckId: "" };
  if (!storageKey) return empty;
  try {
    const encoded = localStorage.getItem(storageKey);
    if (!encoded || encoded.length > 2400) return empty;
    const raw = JSON.parse(encoded);
    if (
      !raw || raw.question_id !== questionId || raw.revision !== revision ||
      raw.phase !== phase
    ) {
      localStorage.removeItem(storageKey);
      return empty;
    }
    return {
      placements: cleanPlacementMap(raw.placements, legalItems, legalTargets),
      appliedAckId: asText(raw.applied_ack_id, "", 100),
    };
  } catch (_) {
    return empty;
  }
};

const writeDraft = (
  storageKey, questionId, revision, phase, placements, appliedAckId = ""
) => {
  if (!storageKey) return;
  const bounded = Object.fromEntries(
    Object.entries(placements).slice(0, MAX_DRAFT_PLACEMENTS)
  );
  try {
    localStorage.setItem(storageKey, JSON.stringify({
      question_id: questionId,
      revision,
      phase,
      placements: bounded,
      applied_ack_id: asText(appliedAckId, "", 100),
    }));
  } catch (_) {
    // Private browsing and disabled storage fall back to this render's memory.
  }
};

const makeDraggable = (parent, item, itemType, className, copyBuilder) => {
  const node = add(parent, "div", `${className} dc-draggable`);
  node.tabIndex = 0;
  node.setAttribute("role", "button");
  node.setAttribute("aria-label", `拿起：${item.title}`);
  node.dataset.itemId = item.id;
  node.dataset.itemType = itemType;
  node.dataset.itemLabel = item.title;
  copyBuilder(node, item);
  return node;
};

const makeDropzone = (parent, item, accepts, className, copyBuilder) => {
  const node = add(parent, "div", `${className} dc-dropzone`);
  node.tabIndex = 0;
  node.setAttribute("role", "button");
  node.setAttribute("aria-label", `放入：${item.title}`);
  node.dataset.targetId = item.id;
  node.dataset.accepts = accepts;
  copyBuilder(node, item);
  return node;
};

const cardCopy = (node, item) => {
  add(node, "div", "dc-card-eyebrow", item.eyebrow);
  add(node, "div", "dc-card-title", item.title);
  if (item.body) add(node, "div", "dc-card-body", item.body);
};

const targetCopy = (node, item, kicker) => {
  add(node, "div", "dc-zone-kicker", kicker);
  add(node, "div", "dc-zone-title", item.title);
  if (item.hint || item.body) add(node, "div", "dc-zone-hint", item.hint || item.body);
};

const phaseDefaults = (phase) => {
  const all = {
    routes: {
      kicker: "PHASE 01 · DUAL CLOCK",
      title: "让事实分别敲响两只钟",
      instruction: "拖动事实卡到利润、现金、两者或暂不触发。手机可先点卡片，再点目标；键盘按 Enter 也能操作。",
      npc: { name: "林叙", role: "经营质量调查员", line: "先分清发生了什么，再决定它属于哪一只钟。数字会说话，但从不替你断句。" },
    },
    hypothesis: {
      kicker: "PHASE 02 · GAP LAB",
      title: "给一百万元差额找一个可核验解释",
      instruction: "把差额令牌放进你认为值得优先调查的假设插槽。这里选的不是结论，而是下一步该查什么。",
      npc: { name: "苏砚", role: "现金流取证顾问", line: "一个解释如果无法被证伪，就不是调查假设，只是听起来顺耳。" },
    },
    orders: {
      kicker: "PHASE 03 · EVIDENCE ORDER",
      title: "把调查动作送进对应的证据口袋",
      instruction: "匹配调查材料与证据目的。管理层承诺可以听，但不能代替可以追溯的证据。",
      npc: { name: "顾言", role: "交叉核验官", line: "证据的证据仍需核验。怀疑一次不难，难的是知道下一次该怀疑什么。" },
    },
    door: {
      kicker: "PHASE 04 · ACCESS GATE",
      title: "签发调查令，进入真实案卷",
      instruction: "把已经签发的调查令拖入门禁扫描器。门后没有标准答案，只有更完整的证据。",
      npc: { name: "沈时", role: "案件调度主管", line: "你的调查令已经成形。别把权限当奖励——它只是意味着，你要为下一次判断承担更多责任。" },
    },
  };
  return all[phase];
};

const renderHeader = (shell, state, phase, phaseIndex, submit, signal) => {
  const topbar = add(shell, "header", "dc-topbar");
  const brand = add(topbar, "div", "dc-brand");
  add(brand, "div", "dc-brand-kicker", "FANGZHENG AI · INVESTIGATION LAB");
  add(brand, "div", "dc-brand-title", asText(state.case_title, "CASE 01｜消失的现金", 100));

  const progress = add(topbar, "nav", "dc-progress");
  progress.setAttribute("aria-label", "第3幕调查进度");
  PHASES.forEach((_, index) => {
    if (index) add(progress, "span", "dc-progress-line");
    const node = add(progress, "span", "dc-progress-node", String(index + 1));
    if (index < phaseIndex) node.classList.add("is-done");
    if (index === phaseIndex) {
      node.classList.add("is-current");
      node.setAttribute("aria-current", "step");
    }
  });

  const status = add(topbar, "div", "dc-status");
  add(status, "strong", "", asText(state.status_label, `第 ${phaseIndex + 1} / 4 段`, 60));
  add(status, "span", "", asText(state.save_label, "本机草稿自动保存", 80));

  const toolbar = add(topbar, "div", "dc-toolbar");
  const controls = [
    ["go_back", "← 上一步"],
    ["rename_player", "修改代号"],
    ["restart_game", "重新开始"],
    ["exit_game", "返回首页"],
  ];
  for (const [action, label] of controls) {
    const button = add(toolbar, "button", "dc-toolbar-button", label);
    button.type = "button";
    button.addEventListener("click", () => submit(action), { signal });
  }
};

const renderNpc = (stage, state, defaults) => {
  const rawNpc = asObject(state.npc);
  const npc = {
    name: asText(rawNpc.name, defaults.name, 40),
    role: asText(rawNpc.role, defaults.role, 80),
    line: asText(rawNpc.line, defaults.line, 280),
    imageUrl: asText(rawNpc.image_url, "", 1000),
  };
  const panel = add(stage, "aside", "dc-npc");
  if (npc.imageUrl) {
    const portrait = add(panel, "div", "dc-npc-portrait");
    portrait.style.backgroundImage = `url(${JSON.stringify(npc.imageUrl)})`;
  } else {
    add(panel, "div", "dc-npc-fallback", npc.name.slice(0, 1));
  }
  const copy = add(panel, "div", "dc-npc-copy");
  add(copy, "div", "dc-npc-role", npc.role);
  add(copy, "div", "dc-npc-name", npc.name);
  add(copy, "p", "dc-npc-line", npc.line);
};

const renderSceneHeader = (scene, state, defaults, countLabel) => {
  const header = add(scene, "div", "dc-scene-header");
  const copy = add(header, "div", "");
  add(copy, "div", "dc-phase-kicker", asText(state.scene_kicker, defaults.kicker, 100));
  add(copy, "h2", "dc-scene-heading", asText(state.scene_title, defaults.title, 140));
  add(copy, "p", "dc-scene-instruction", asText(state.instruction, defaults.instruction, 420));
  if (countLabel) add(header, "div", "dc-scene-count", countLabel);
};

const addPlacementChips = (zone, targetId, placements, itemsById) => {
  const matches = Object.entries(placements).filter(([, value]) => value === targetId);
  if (!matches.length) return;
  const chips = add(zone, "div", "dc-zone-chips");
  for (const [itemId] of matches) {
    const item = itemsById.get(itemId);
    const chip = add(chips, "button", "dc-zone-chip dc-placement-chip", item?.title || itemId);
    chip.type = "button";
    chip.dataset.itemId = itemId;
    chip.setAttribute("aria-label", `撤回：${item?.title || itemId}`);
    chip.title = "点按可撤回并重新放置";
  }
};

const addPhaseSubmit = (scene, label, helper) => {
  const action = add(scene, "div", "dc-phase-action");
  if (helper) add(action, "span", "", helper);
  const button = add(action, "button", "dc-phase-submit", label);
  button.type = "button";
  return button;
};

const renderClassification = (workarea, state, defaults, collection, placements) => {
  const scene = add(workarea, "section", "dc-scene");
  const remaining = collection.items.filter((item) => !(item.id in placements));
  renderSceneHeader(
    scene, state, defaults,
    `${Object.keys(placements).length} / ${collection.items.length} 已投放`
  );
  const grid = add(scene, "div", "dc-card-grid");
  for (const item of remaining) {
    makeDraggable(grid, item, "fact", "dc-fact-card", cardCopy);
  }
  if (!remaining.length) add(grid, "div", "dc-empty", "事实卡已全部送入双时钟，等待核验回执。 ");

  const byId = new Map(collection.items.map((item) => [item.id, item]));
  const zones = add(scene, "div", "dc-zone-grid");
  for (const item of collection.targets) {
    const zone = makeDropzone(zones, item, "fact", "dc-zone", (node, target) => {
      targetCopy(node, target, "CLOCK CHANNEL");
    });
    addPlacementChips(zone, item.id, placements, byId);
  }
  const allFactsPlaced = collection.items.length === 6 &&
    collection.items.every((item) => item.id in placements);
  const submitButton = addPhaseSubmit(
    scene,
    "提交双时钟核验",
    allFactsPlaced
      ? "六张事实卡已有明确归属，可以提交核验。"
      : "先让六张事实卡全部进入双时钟、同时触发区或边界托盘。",
  );
  submitButton.disabled = !allFactsPlaced;
  submitButton.setAttribute("aria-disabled", String(!allFactsPlaced));
};

const renderHypothesis = (workarea, state, defaults, collection, placements) => {
  const scene = add(workarea, "section", "dc-scene");
  renderSceneHeader(scene, state, defaults, Object.keys(placements).length ? "假设已送审" : "待放置差额");
  const metrics = asObject(state.metrics);
  const board = add(scene, "div", "dc-clock-board");
  const profitClock = add(board, "div", "dc-clock");
  const profitCopy = add(profitClock, "div", "");
  add(profitCopy, "div", "dc-clock-value", asText(metrics.profit, "+50 万元", 60));
  add(profitCopy, "div", "dc-clock-label", "利润时钟");

  const center = add(board, "div", "dc-hypothesis-center");
  const token = collection.items[0];
  if (token && !(token.id in placements)) {
    makeDraggable(center, token, "gap", "dc-gap-token", (node, item) => {
      add(node, "strong", "", item.title || "100 万元");
      add(node, "span", "", item.body || "利润—现金差额");
    });
  } else {
    add(center, "div", "dc-gap-token", "差额已进入假设审查");
  }

  const cashClock = add(board, "div", "dc-clock");
  const cashCopy = add(cashClock, "div", "");
  add(cashCopy, "div", "dc-clock-value", asText(metrics.cash, "−50 万元", 60));
  add(cashCopy, "div", "dc-clock-label", "现金时钟");

  const slots = add(scene, "div", "dc-hypothesis-grid");
  for (const item of collection.targets) {
    const slot = makeDropzone(slots, item, "gap", "dc-hypothesis-slot", (node, target) => {
      add(node, "div", "dc-slot-title", target.title);
      if (target.hint || target.body) add(node, "div", "dc-slot-hint", target.hint || target.body);
    });
    const tokenId = Object.keys(placements).find((id) => placements[id] === item.id);
    if (tokenId) {
      const chip = add(slot, "button", "dc-zone-chip dc-placement-chip", "差额令牌 · 点此撤回");
      chip.type = "button";
      chip.dataset.itemId = tokenId;
      chip.setAttribute("aria-label", "撤回差额令牌");
    }
  }
  const hypothesisPlaced = collection.items.length === 1 &&
    collection.items.every((item) => item.id in placements);
  const submitButton = addPhaseSubmit(
    scene,
    "锁定调查假设",
    hypothesisPlaced
      ? "差额已进入待核验假设，可以提交。"
      : "先把差额令牌放进一个可被后续证据支持或推翻的假设插槽。",
  );
  submitButton.disabled = !hypothesisPlaced;
  submitButton.setAttribute("aria-disabled", String(!hypothesisPlaced));
};

const renderOrders = (workarea, state, defaults, collection, placements) => {
  const scene = add(workarea, "section", "dc-scene");
  renderSceneHeader(scene, state, defaults, `${Object.keys(placements).length} / 4 材料已有去向`);
  const layout = add(scene, "div", "dc-orders-layout");
  const rack = add(layout, "div", "dc-material-rack");
  add(rack, "div", "dc-rack-title", "可签发的调查材料");
  const materialList = add(rack, "div", "dc-material-list");
  const remaining = collection.items.filter((item) => !(item.id in placements));
  layout.classList.toggle("is-rack-empty", remaining.length === 0);
  for (const item of remaining) {
    makeDraggable(materialList, item, "material", "dc-material-card", (node, material) => {
      add(node, "strong", "", material.title);
      if (material.body) add(node, "span", "", material.body);
    });
  }
  if (!remaining.length) add(materialList, "div", "dc-empty", "材料架已清空");

  const board = add(layout, "div", "dc-pocket-board");
  add(board, "div", "dc-rack-title", "证据目的口袋");
  const pockets = add(board, "div", "dc-pocket-list");
  const byId = new Map(collection.items.map((item) => [item.id, item]));
  for (const item of collection.targets) {
    const pocket = makeDropzone(pockets, item, "material", "dc-pocket", (node, target) => {
      add(node, "div", "dc-pocket-kicker", "EVIDENCE POCKET");
      add(node, "div", "dc-pocket-title", target.title);
      if (target.hint) add(node, "div", "dc-zone-hint", target.hint);
    });
    const inserted = Object.entries(placements).find(([, target]) => target === item.id);
    if (inserted) {
      const filled = add(pocket, "button", "dc-pocket-filled dc-placement-chip", `已放入：${byId.get(inserted[0])?.title || inserted[0]}`);
      filled.type = "button";
      filled.dataset.itemId = inserted[0];
      filled.setAttribute("aria-label", `撤回：${byId.get(inserted[0])?.title || inserted[0]}`);
    }
  }
  const usedTargets = new Set(Object.values(placements));
  const allMaterialsPlaced = collection.items.length === 4 &&
    collection.items.every((item) => item.id in placements) &&
    usedTargets.size === 4;
  const submitButton = addPhaseSubmit(
    scene,
    "签发三路调查令",
    allMaterialsPlaced
      ? "四件材料已有明确去向，可以签发。"
      : "三项进入证据口袋，一项进入弃置区；四件材料都必须有明确去向。",
  );
  submitButton.disabled = !allMaterialsPlaced;
  submitButton.setAttribute("aria-disabled", String(!allMaterialsPlaced));
};

const renderDoor = (workarea, state, defaults, collection, placements) => {
  const scene = add(workarea, "section", "dc-scene");
  renderSceneHeader(scene, state, defaults, Object.keys(placements).length ? "门禁核验中" : "门禁待授权");
  const layout = add(scene, "div", "dc-door-layout");
  const order = collection.items[0];
  if (order && !(order.id in placements)) {
    makeDraggable(layout, order, "order", "dc-order-token", (node, item) => {
      add(node, "div", "dc-order-seal", "SIGNED · INVESTIGATION ORDER");
      add(node, "div", "dc-order-title", item.title || "调查令");
      add(node, "div", "dc-order-meta", item.body || "双时钟差额已建立，调查动作已完成证据匹配。拖入门禁以开启真实案卷。 ");
    });
  } else {
    add(layout, "div", "dc-empty", "调查令已递交");
  }
  const doorItem = collection.targets[0] || { id: "evidence-door", title: "证据室门禁" };
  const door = makeDropzone(layout, doorItem, "order", "dc-door", (node, target) => {
    add(node, "span", "dc-door-light");
    const scanner = add(node, "div", "dc-door-scanner");
    scanner.textContent = asText(target.hint || target.body, "将签发的调查令拖到这里\n开启真实案卷", 160);
    scanner.style.whiteSpace = "pre-line";
  });
  if (Object.values(placements).includes(doorItem.id)) door.classList.add("is-compatible");
};

const renderKeepsake = (workarea, state, submit, signal) => {
  const discovered = state.keepsake_discovered === true;
  if (discovered) {
    const inventory = add(workarea, "div", "dc-keepsake-inventory");
    inventory.setAttribute("aria-label", "物品栏：双时钟校准尺");
    add(inventory, "span", "", "⌁");
    add(inventory, "strong", "", "双时钟校准尺");
    return;
  }
  const keepsake = add(workarea, "button", "dc-keepsake-clue");
  keepsake.type = "button";
  keepsake.setAttribute("aria-label", "检查桌沿一段不寻常的校准刻度");
  keepsake.title = "这段刻度似乎不属于桌面";
  for (let index = 0; index < 7; index += 1) add(keepsake, "i", "");
  keepsake.addEventListener(
    "click", () => submit("discover_keepsake"), { signal }
  );
};

const renderFeedback = (shell, state, announce) => {
  const raw = asObject(state.feedback);
  const tone = ["neutral", "success", "warning", "error"].includes(raw.tone) ? raw.tone : "neutral";
  const panel = add(shell, "footer", "dc-feedback");
  panel.dataset.tone = tone;
  const copy = add(panel, "div", "dc-feedback-copy");
  add(copy, "div", "dc-feedback-label", asText(raw.label, "调查室回执", 50));
  const title = add(copy, "div", "dc-feedback-title", asText(raw.title, "拖动、点选或使用键盘开始操作", 160));
  add(copy, "div", "dc-feedback-message", asText(raw.message, "每次投放都由 Python 重新核验；画面里不保存答案。", 320));
  add(panel, "div", "dc-control-hint", "拖拽 · 点选后点目标 · Tab + Enter");
  announce.textContent = title.textContent;
};

const installInteractions = ({ root, controller, submit, announce, updateDraft }) => {
  const signal = controller.signal;
  let selected = null;
  let pointer = null;
  let ghost = null;
  let movedRecently = false;

  const allDraggables = () => [...root.querySelectorAll(".dc-draggable")];
  const allTargets = () => [...root.querySelectorAll(".dc-dropzone")];
  const compatible = (target, itemType) => (
    asText(target.dataset.accepts, "").split(/\s+/).includes(itemType)
  );
  const markTargets = (itemType, active) => {
    for (const target of allTargets()) {
      target.classList.toggle("is-compatible", active && compatible(target, itemType));
    }
  };
  const choose = (node) => {
    if (selected?.node === node) {
      node.classList.remove("is-selected");
      markTargets(selected.type, false);
      selected = null;
      announce.textContent = "已放下材料";
      return;
    }
    if (selected) selected.node.classList.remove("is-selected");
    selected = {
      node,
      id: node.dataset.itemId,
      type: node.dataset.itemType,
      label: node.dataset.itemLabel,
    };
    node.classList.add("is-selected");
    markTargets(selected.type, true);
    announce.textContent = `已拿起${selected.label}，请选择放置位置`;
  };
  const drop = (item, target) => {
    if (!item || !target || !compatible(target, item.type)) {
      announce.textContent = "这个位置不接收当前材料";
      return;
    }
    if (item.type === "order") {
      submit("open_door");
    } else {
      updateDraft(item.id, target.dataset.targetId);
    }
    target.classList.add("is-dragover");
    setTimeout(() => target.classList.remove("is-dragover"), 420);
    if (item.node) {
      item.node.classList.remove("is-selected");
      item.node.animate?.(
        [
          { opacity: 1, transform: "scale(1)" },
          { opacity: .25, transform: "scale(.82) translateY(8px)" },
        ],
        { duration: 230, easing: "ease-out", fill: "forwards" },
      );
    }
    markTargets(item.type, false);
    selected = null;
  };
  const targetAt = (x, y, type) => (
    document.elementsFromPoint(x, y).find(
      (node) => node.classList?.contains("dc-dropzone") && compatible(node, type)
    ) || null
  );
  const endPointer = (event, cancelled = false) => {
    if (!pointer) return;
    const active = pointer;
    pointer = null;
    const target = cancelled ? null : targetAt(event.clientX, event.clientY, active.type);
    ghost?.remove();
    ghost = null;
    for (const node of allTargets()) node.classList.remove("is-dragover");
    markTargets(active.type, false);
    if (active.moved) {
      movedRecently = true;
      setTimeout(() => { movedRecently = false; }, 80);
      if (target) drop(active, target);
      else announce.textContent = "材料已回到原位";
    }
  };

  for (const node of allDraggables()) {
    node.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || root.classList.contains("is-pending")) return;
      pointer = {
        id: node.dataset.itemId,
        type: node.dataset.itemType,
        label: node.dataset.itemLabel,
        node,
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        moved: false,
      };
      node.setPointerCapture?.(event.pointerId);
    }, { signal });
    node.addEventListener("pointermove", (event) => {
      if (!pointer || pointer.pointerId !== event.pointerId) return;
      const distance = Math.hypot(event.clientX - pointer.startX, event.clientY - pointer.startY);
      if (!pointer.moved && distance > 7) {
        pointer.moved = true;
        ghost = add(document.body, "div", "dc-drag-ghost", pointer.label);
        markTargets(pointer.type, true);
      }
      if (!pointer.moved) return;
      event.preventDefault();
      ghost.style.left = `${event.clientX}px`;
      ghost.style.top = `${event.clientY}px`;
      for (const target of allTargets()) target.classList.remove("is-dragover");
      targetAt(event.clientX, event.clientY, pointer.type)?.classList.add("is-dragover");
    }, { signal });
    node.addEventListener("pointerup", (event) => endPointer(event), { signal });
    node.addEventListener("pointercancel", (event) => endPointer(event, true), { signal });
    node.addEventListener("click", () => {
      if (!movedRecently && !root.classList.contains("is-pending")) choose(node);
    }, { signal });
    node.addEventListener("keydown", (event) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        choose(node);
      } else if (event.key === "Escape" && selected) {
        choose(selected.node);
      }
    }, { signal });
  }

  for (const target of allTargets()) {
    target.addEventListener("click", () => {
      if (selected && !root.classList.contains("is-pending")) drop(selected, target);
      else if (!selected) announce.textContent = "请先拿起一张材料卡";
    }, { signal });
    target.addEventListener("keydown", (event) => {
      if (["Enter", " "].includes(event.key)) {
        event.preventDefault();
        if (selected && !root.classList.contains("is-pending")) drop(selected, target);
        else announce.textContent = "请先拿起一张材料卡";
      }
    }, { signal });
  }
};

export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const payload = asObject(data);
  const state = asObject(payload.state);
  const questionId = asText(payload.question_id, "cash-dual-clock", 80);
  const revision = Number.isInteger(payload.revision) && payload.revision >= 0
    ? payload.revision : 0;
  const requestedPhase = state.phase === "classification" ? "routes" : state.phase;
  const phase = PHASES.includes(requestedPhase) ? requestedPhase : "routes";
  const phaseIndex = PHASES.indexOf(phase);
  const collection = phaseCollection(state, phase);
  const legalItems = new Set(collection.items.map((item) => item.id));
  const legalTargets = new Set(collection.targets.map((item) => item.id));
  const storageKey = asText(payload.draft_storage_key, "", 180);
  const serverPlacements = cleanPlacementMap(
    state.placements || state.accepted, legalItems, legalTargets
  );
  const loadedDraft = readDraft(
    storageKey, questionId, revision, phase, legalItems, legalTargets
  );
  let draftPlacements = loadedDraft.placements;
  let appliedAckId = loadedDraft.appliedAckId;
  const serverAckId = asText(state.acknowledged_command_id, "", 100);
  const hasNewAcknowledgement = Boolean(
    serverAckId && serverAckId !== appliedAckId
  );
  if (hasNewAcknowledgement) {
    draftPlacements = serverPlacements;
    appliedAckId = serverAckId;
    if (Object.keys(draftPlacements).length) {
      writeDraft(
        storageKey, questionId, revision, phase, draftPlacements, appliedAckId
      );
    } else {
      writeDraft(storageKey, questionId, revision, phase, {}, appliedAckId);
    }
  } else {
    draftPlacements = { ...serverPlacements, ...draftPlacements };
  }

  const root = parentElement.querySelector(".dc-game");
  if (!root) return;
  root.className = "dc-game";
  let controller = null;
  let pendingTimer = null;
  let announce = null;
  let redraw = () => {};

  const submit = (action, details = {}) => {
    const command = {
      schema_version: SCHEMA_VERSION,
      command_id: makeId(),
      question_id: questionId,
      revision,
      action,
      ...details,
    };
    root.classList.add("is-pending");
    if (announce) announce.textContent = "操作已送往调查终端核验";
    setTriggerValue("command", command);
    clearTimeout(pendingTimer);
    pendingTimer = setTimeout(() => root.classList.remove("is-pending"), 1400);
  };
  const updateDraft = (itemId, targetId) => {
    if (!legalItems.has(itemId) || !legalTargets.has(targetId)) return;
    if (phase === "hypothesis") draftPlacements = {};
    if (phase === "orders") {
      for (const [placedItem, placedTarget] of Object.entries(draftPlacements)) {
        if (placedTarget === targetId) delete draftPlacements[placedItem];
      }
    }
    draftPlacements[itemId] = targetId;
    draftPlacements = cleanPlacementMap(draftPlacements, legalItems, legalTargets);
    writeDraft(
      storageKey, questionId, revision, phase, draftPlacements, appliedAckId
    );
    redraw();
  };
  const removeDraft = (itemId) => {
    if (!(itemId in draftPlacements)) return;
    delete draftPlacements[itemId];
    writeDraft(
      storageKey, questionId, revision, phase, draftPlacements, appliedAckId
    );
    redraw();
  };
  const submitPhase = () => {
    if (phase === "routes") {
      submit("submit_routes", { bins: { ...draftPlacements } });
    } else if (phase === "hypothesis") {
      submit("submit_hypothesis", {
        hypothesis_id: Object.values(draftPlacements)[0] || "",
      });
    } else if (phase === "orders") {
      const pockets = {};
      let discardedItem = "";
      for (const [itemId, targetId] of Object.entries(draftPlacements)) {
        if (targetId === "discarded") discardedItem = itemId;
        else pockets[targetId] = itemId;
      }
      submit("submit_orders", {
        pockets,
        discarded: discardedItem ? [discardedItem] : [],
      });
    }
  };

  redraw = () => {
    controller?.abort();
    controller = new AbortController();
    root.replaceChildren();
    const localAnnounce = add(root, "div", "dc-a11y-status");
    localAnnounce.setAttribute("role", "status");
    localAnnounce.setAttribute("aria-live", "polite");
    localAnnounce.style.cssText = "position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);";
    announce = localAnnounce;

    const shell = add(root, "div", "dc-shell");
    renderHeader(
      shell, state, phase, phaseIndex, submit, controller.signal
    );
    const stage = add(shell, "div", "dc-stage");
    stage.dataset.phase = phase;
    const defaults = phaseDefaults(phase);
    renderNpc(stage, state, defaults.npc);
    const workarea = add(stage, "div", "dc-workarea");
    if (phase === "routes") {
      renderClassification(workarea, state, defaults, collection, draftPlacements);
    } else if (phase === "hypothesis") {
      renderHypothesis(workarea, state, defaults, collection, draftPlacements);
    } else if (phase === "orders") {
      renderOrders(workarea, state, defaults, collection, draftPlacements);
    } else {
      renderDoor(workarea, state, defaults, collection, draftPlacements);
    }
    renderKeepsake(workarea, state, submit, controller.signal);
    renderFeedback(shell, state, announce);
    installInteractions({ root, controller, submit, announce, updateDraft });
    root.querySelector(".dc-phase-submit")?.addEventListener(
      "click", submitPhase, { signal: controller.signal }
    );
    for (const chip of root.querySelectorAll(".dc-placement-chip")) {
      chip.addEventListener(
        "click", () => removeDraft(chip.dataset.itemId),
        { signal: controller.signal },
      );
    }
  };
  redraw();

  return () => {
    controller?.abort();
    clearTimeout(pendingTimer);
    document.querySelectorAll(".dc-drag-ghost").forEach((node) => node.remove());
  };
}
