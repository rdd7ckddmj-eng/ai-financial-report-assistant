const SCHEMA_VERSION = 1;
const PHASES = new Set(["reading", "classification", "chain"]);

const asObject = (value) => (
  value && typeof value === "object" && !Array.isArray(value) ? value : {}
);
const asList = (value) => (Array.isArray(value) ? value : []);
const asText = (value, fallback = "", max = 240) => {
  if (typeof value !== "string") return fallback;
  const clean = value.trim();
  return clean ? clean.slice(0, max) : fallback;
};
const asInteger = (value, fallback = 0, min = 0, max = 999) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(number)));
};
const unique = (items) => [...new Set(items)];

const add = (parent, tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  parent.append(node);
  return node;
};

const makeCommandId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `lab-${Date.now()}-${Math.random().toString(16).slice(2, 12)}`;
};

const cleanDocument = (raw, index) => {
  const item = asObject(raw);
  return {
    id: asText(item.document_id, `document-${index + 1}`, 80),
    location: asText(item.location, `证物袋 ${index + 1}`, 100),
    title: asText(item.title, `卷宗材料 ${index + 1}`, 150),
    type: asText(item.document_type, "待核材料", 100),
    body: asText(item.body, "材料正文等待恢复。", 2200),
    footer: asText(item.footer, "来源信息等待恢复。", 700),
  };
};

const cleanMap = (value, allowedKeys, allowedValues = null) => {
  const result = {};
  Object.entries(asObject(value)).slice(0, 30).forEach(([key, rawValue]) => {
    if (!allowedKeys.has(key) || typeof rawValue !== "string") return;
    if (allowedValues && !allowedValues.has(rawValue)) return;
    result[key] = rawValue;
  });
  return result;
};

const legalIdList = (value, allowed, max = 40) => unique(
  asList(value)
    .filter((item) => typeof item === "string" && allowed.has(item))
    .slice(0, max),
);

const safeLoadDraft = (storageKey) => {
  try {
    const raw = globalThis.localStorage?.getItem(storageKey);
    if (!raw || raw.length > 24000) return {};
    return asObject(JSON.parse(raw));
  } catch {
    return {};
  }
};

const safeSaveDraft = (storageKey, draft) => {
  try {
    globalThis.localStorage?.setItem(storageKey, JSON.stringify(draft));
  } catch {
    // Private browsing/storage denial must not break the game.
  }
};

export default function renderEvidenceLab(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".evidence-lab");
  if (!root) return undefined;

  const payload = asObject(data);
  const state = asObject(payload.state);
  const task = asObject(state.task);
  const taskId = asText(payload.task_id, asText(task.task_id, "", 120), 120);
  const revision = asInteger(payload.revision, 0, 0, 1e7);
  const phase = PHASES.has(state.phase) ? state.phase : "reading";
  const storageKey = asText(
    payload.draft_storage_key,
    "wfz_cash_evidence_lab_draft",
    160,
  );
  const progress = asObject(state.progress);
  const evaluation = asObject(state.evaluation);
  const acknowledgedId = asText(state.acknowledged_command_id, "", 100);

  const readingTask = asObject(task.reading);
  const documents = asList(readingTask.documents).slice(0, 12).map(cleanDocument);
  const documentIds = new Set(documents.map((item) => item.id));
  const fields = asList(readingTask.field_options).slice(0, 48).map((raw, index) => {
    const item = asObject(raw);
    return {
      id: asText(item.field_id, `field-${index + 1}`, 90),
      documentId: asText(item.document_id, "", 80),
      label: asText(item.label, `候选字段 ${index + 1}`, 220),
    };
  }).filter((item) => documentIds.has(item.documentId));
  const fieldIds = new Set(fields.map((item) => item.id));

  const classificationTask = asObject(task.classification);
  const classes = asList(classificationTask.classes).slice(0, 6).map((raw, index) => {
    const item = asObject(raw);
    return {
      id: asText(item.class_id, `class-${index + 1}`, 80),
      label: asText(item.label, `归档区 ${index + 1}`, 90),
    };
  });
  const classIds = new Set(classes.map((item) => item.id));
  const classificationItems = asList(classificationTask.items).slice(0, 18).map((raw, index) => {
    const item = asObject(raw);
    return {
      id: asText(item.item_id, `item-${index + 1}`, 90),
      label: asText(item.label, `待归档陈述 ${index + 1}`, 260),
    };
  });
  const classificationIds = new Set(classificationItems.map((item) => item.id));

  const chainTask = asObject(task.chain);
  const claims = asList(chainTask.claims).slice(0, 12).map((raw, index) => {
    const item = asObject(raw);
    return {
      id: asText(item.claim_id, `claim-${index + 1}`, 90),
      label: asText(item.label, `研究主张 ${index + 1}`, 240),
    };
  });
  const claimIds = new Set(claims.map((item) => item.id));

  const serverAcceptedFields = new Set(legalIdList(
    progress.accepted_field_ids,
    fieldIds,
  ));
  const serverAcceptedPlacements = cleanMap(
    progress.accepted_placements,
    classificationIds,
    classIds,
  );
  const serverAcceptedLinks = cleanMap(
    progress.accepted_links,
    claimIds,
    documentIds,
  );
  const serverViewed = legalIdList(progress.viewed_document_ids, documentIds, 12);
  const acceptedIds = new Set(legalIdList(
    evaluation.accepted,
    phase === "reading" ? fieldIds : phase === "classification" ? classificationIds : claimIds,
  ));
  const rejectedIds = new Set(legalIdList(
    evaluation.rejected,
    phase === "reading" ? fieldIds : phase === "classification" ? classificationIds : claimIds,
  ));

  const freshDraft = {
    version: 1,
    task_id: taskId,
    revision,
    phase,
    applied_ack_id: "",
    applied_evaluation_signature: "",
    active_document_id: documents[0]?.id || "",
    viewed_document_ids: [],
    marked_field_ids: [],
    placements: {},
    links: {},
  };
  const stored = safeLoadDraft(storageKey);
  let draft = (
    stored.version === 1 &&
    stored.task_id === taskId &&
    stored.revision === revision &&
    stored.phase === phase
  ) ? { ...freshDraft, ...stored } : freshDraft;

  draft.active_document_id = documentIds.has(draft.active_document_id)
    ? draft.active_document_id
    : documents[0]?.id || "";
  draft.viewed_document_ids = legalIdList(draft.viewed_document_ids, documentIds, 12);
  draft.marked_field_ids = legalIdList(draft.marked_field_ids, fieldIds);
  draft.placements = cleanMap(draft.placements, classificationIds, classIds);
  draft.links = cleanMap(draft.links, claimIds, documentIds);

  const expectedEvaluationAction = {
    reading: "submit_reading",
    classification: "submit_classification",
    chain: "submit_chain",
  }[phase];
  const evaluationSignature = (
    evaluation.phase === phase &&
    evaluation.action === expectedEvaluationAction
  ) ? JSON.stringify({
    command_id: asText(evaluation.command_id, "", 100),
    phase: evaluation.phase,
    action: evaluation.action,
    accepted: [...acceptedIds],
    rejected: [...rejectedIds],
    clean_payload: asObject(evaluation.clean_payload),
  }).slice(0, 12000) : "";
  const hasFreshEvaluation = Boolean(
    evaluationSignature &&
    draft.applied_evaluation_signature !== evaluationSignature
  );

  if (hasFreshEvaluation) {
    draft.viewed_document_ids = unique([
      ...draft.viewed_document_ids,
      ...serverViewed,
    ]);
    if (phase === "reading") {
      draft.marked_field_ids = unique([
        ...draft.marked_field_ids.filter((id) => !rejectedIds.has(id)),
        ...serverAcceptedFields,
        ...acceptedIds,
      ]);
    } else if (phase === "classification") {
      rejectedIds.forEach((id) => delete draft.placements[id]);
      Object.assign(draft.placements, serverAcceptedPlacements);
      const cleanPayload = asObject(evaluation.clean_payload);
      const submitted = cleanMap(cleanPayload.placements, classificationIds, classIds);
      acceptedIds.forEach((id) => {
        if (submitted[id]) draft.placements[id] = submitted[id];
      });
    } else {
      rejectedIds.forEach((id) => delete draft.links[id]);
      Object.assign(draft.links, serverAcceptedLinks);
      const cleanPayload = asObject(evaluation.clean_payload);
      const submitted = cleanMap(cleanPayload.links, claimIds, documentIds);
      acceptedIds.forEach((id) => {
        if (submitted[id]) draft.links[id] = submitted[id];
      });
    }
    draft.applied_evaluation_signature = evaluationSignature;
  }
  draft.viewed_document_ids = unique([...draft.viewed_document_ids, ...serverViewed]);
  draft.marked_field_ids = unique([...draft.marked_field_ids, ...serverAcceptedFields]);
  Object.assign(draft.placements, serverAcceptedPlacements);
  Object.assign(draft.links, serverAcceptedLinks);
  if (acknowledgedId) draft.applied_ack_id = acknowledgedId;
  if (phase === "reading" && draft.active_document_id) {
    draft.viewed_document_ids = unique([
      ...draft.viewed_document_ids,
      draft.active_document_id,
    ]);
  }
  safeSaveDraft(storageKey, draft);

  const shell = document.createElement("section");
  shell.className = `lab-shell phase-${phase}`;
  const controller = new AbortController();
  const { signal } = controller;
  let pendingCommand = false;
  let selectedCard = null;
  let drag = null;
  let dragGhost = null;
  let resizeObserver = null;

  const announce = add(shell, "div", "lab-a11y-status");
  announce.setAttribute("role", "status");
  announce.setAttribute("aria-live", "polite");

  const save = () => safeSaveDraft(storageKey, draft);
  const submit = (action, extra = {}) => {
    if (pendingCommand) return;
    pendingCommand = true;
    announce.textContent = "已把当前实验台送往证据终端核验";
    shell.classList.add("is-pending");
    setTriggerValue("command", {
      schema_version: SCHEMA_VERSION,
      command_id: makeCommandId(),
      task_id: taskId,
      revision,
      action,
      ...extra,
    });
  };

  const hud = add(shell, "header", "lab-hud");
  const brand = add(hud, "div", "lab-brand");
  add(brand, "small", "", "FANGZHENG AI · EVIDENCE LAB");
  add(brand, "strong", "", "《消失的现金》");
  const phaseCopy = {
    reading: ["05", "逐页解码", "字缝里的时间"],
    classification: ["06", "时间边界", "关掉事后诸葛亮"],
    chain: ["07", "证据架构", "让四环证据闭合"],
  }[phase];
  const phaseTitle = add(hud, "div", "lab-phase-title");
  add(phaseTitle, "small", "", `${phaseCopy[0]} · CONTINUOUS LAB`);
  add(phaseTitle, "strong", "", `${phaseCopy[1]}｜${phaseCopy[2]}`);
  const identity = add(hud, "div", "lab-identity");
  add(identity, "small", "", "调查员");
  add(identity, "strong", "", asText(state.player_name, "见习研究员", 40));
  const toolbar = add(hud, "nav", "lab-toolbar");
  toolbar.setAttribute("aria-label", "案件操作");
  [
    ["go_back", "←", "上一步"],
    ["rename_player", "名", "修改代号"],
    ["restart_game", "↻", "重新开始"],
    ["exit_game", "⌂", "退出案件"],
  ].forEach(([action, icon, label]) => {
    const button = add(toolbar, "button", "lab-toolbar-button");
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    add(button, "b", "", icon);
    add(button, "span", "", label);
    button.addEventListener("click", () => submit(action), { signal });
  });

  const body = add(shell, "div", "lab-body");
  const stage = add(body, "main", "lab-stage");
  const rail = add(body, "aside", "lab-mentor-rail");
  const mentorDefaults = {
    reading: ["裴叙言", "材料解码师", "读过材料不等于读懂；限制词往往比数字更昂贵。", "/app/static/cash-game-mentor-05.png"],
    classification: ["苏棱", "交叉核验官", "期后证据可以验证后来发生了什么，却不能倒流成年末事实。", "/app/static/cash-game-mentor-06.png"],
    chain: ["顾临川", "因果架构师", "每条主张只问一个最直接的问题；一份材料也只能先回答它真正知道的。", "/app/static/cash-game-mentor-07.png"],
  }[phase];
  const npc = asObject(state.npc);
  const portrait = add(rail, "img", "lab-mentor-image");
  portrait.src = asText(npc.image_url, mentorDefaults[3], 300);
  portrait.alt = `${asText(npc.name, mentorDefaults[0], 40)}，${asText(npc.role, mentorDefaults[1], 70)}`;
  const mentorCopy = add(rail, "div", "lab-mentor-copy");
  add(mentorCopy, "small", "", asText(npc.role, mentorDefaults[1], 70));
  add(mentorCopy, "strong", "", asText(npc.name, mentorDefaults[0], 40));
  add(mentorCopy, "p", "", asText(npc.line, mentorDefaults[2], 260));
  if (Boolean(state.keepsake_discovered)) {
    const ownedKeepsake = {
      reading: ["▥", "页边墨签"],
      classification: ["◇", "双面棱镜"],
      chain: ["⌘", "因果链扣"],
    }[phase];
    const inventory = add(rail, "div", "lab-keepsake-owned");
    add(inventory, "b", "", ownedKeepsake[0]);
    add(inventory, "span", "", `物品栏｜${ownedKeepsake[1]}`);
  }

  const evaluationFeedback = asText(evaluation.feedback, "", 400);
  const feedback = asObject(state.feedback);
  const feedbackBox = add(rail, "section", "lab-feedback");
  feedbackBox.dataset.tone = asText(feedback.tone, rejectedIds.size ? "warning" : "info", 20);
  add(feedbackBox, "small", "", "证据终端");
  add(
    feedbackBox,
    "strong",
    "",
    asText(feedback.title, evaluation.complete ? "本幕核验完成" : "当前实验台", 100),
  );
  add(
    feedbackBox,
    "p",
    "",
    evaluationFeedback || asText(feedback.message, "正确动作会锁定；错误只退回当前卡片。", 280),
  );

  const setSelected = (kind, id, element) => {
    shell.querySelectorAll(".is-keyboard-selected").forEach((node) => {
      node.classList.remove("is-keyboard-selected");
      node.setAttribute("aria-pressed", "false");
    });
    selectedCard = { kind, id };
    element.classList.add("is-keyboard-selected");
    element.setAttribute("aria-pressed", "true");
    announce.textContent = "已选中卡片；请选择目标区域";
  };

  const clearSelected = () => {
    shell.querySelectorAll(".is-keyboard-selected").forEach((node) => {
      node.classList.remove("is-keyboard-selected");
      node.setAttribute("aria-pressed", "false");
    });
    selectedCard = null;
  };

  const startDrag = (event, kind, id, element) => {
    if (event.button !== 0 || element.dataset.locked === "true") return;
    drag = {
      pointerId: event.pointerId,
      kind,
      id,
      element,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    };
    element.setPointerCapture?.(event.pointerId);
  };

  const bindDraggable = (element, kind, id) => {
    element.addEventListener("pointerdown", (event) => {
      startDrag(event, kind, id, element);
    }, { signal });
    element.addEventListener("click", () => {
      if (element.dataset.locked === "true") return;
      setSelected(kind, id, element);
    }, { signal });
    element.addEventListener("keydown", (event) => {
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        if (element.dataset.locked !== "true") setSelected(kind, id, element);
      }
    }, { signal });
  };

  const updateDrag = (event) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
    if (distance < 7 && !drag.moved) return;
    drag.moved = true;
    event.preventDefault();
    if (!dragGhost) {
      dragGhost = add(shell, "div", "lab-drag-ghost", drag.element.textContent || "证据卡");
    }
    dragGhost.style.left = `${event.clientX}px`;
    dragGhost.style.top = `${event.clientY}px`;
  };

  const finishDrag = (event) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const current = drag;
    drag = null;
    dragGhost?.remove();
    dragGhost = null;
    current.element.releasePointerCapture?.(event.pointerId);
    if (!current.moved) return;
    const drop = document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-drop-kind]");
    if (drop) {
      drop.dispatchEvent(new CustomEvent("labdrop", {
        bubbles: true,
        detail: { kind: current.kind, id: current.id },
      }));
    }
  };
  document.addEventListener("pointermove", updateDrag, { signal, passive: false });
  document.addEventListener("pointerup", finishDrag, { signal });
  document.addEventListener("pointercancel", finishDrag, { signal });

  const maybeRenderKeepsake = (unlocked) => {
    if (!unlocked || Boolean(state.keepsake_discovered)) return;
    const clue = add(stage, "button", `lab-keepsake-clue phase-${phase}`);
    clue.type = "button";
    clue.title = "实验台边缘似乎夹着一件不属于卷宗的东西";
    clue.setAttribute("aria-label", "检查实验台边缘的异常物件");
    add(clue, "span", "", phase === "reading" ? "▥" : phase === "classification" ? "◇" : "⌘");
    clue.addEventListener("click", () => submit("discover_keepsake"), { signal });
  };

  const renderReading = () => {
    stage.classList.add("reading-stage");
    const navigator = add(stage, "nav", "lab-document-rack");
    navigator.setAttribute("aria-label", "六份现场材料");
    const activeIndex = Math.max(0, documents.findIndex((item) => item.id === draft.active_document_id));

    const openDocument = (documentId) => {
      if (!documentIds.has(documentId)) return;
      draft.active_document_id = documentId;
      draft.viewed_document_ids = unique([...draft.viewed_document_ids, documentId]);
      save();
      renderEvidenceLab(component);
    };

    documents.forEach((document, index) => {
      const button = add(navigator, "button", "lab-document-tab");
      button.type = "button";
      button.dataset.active = String(document.id === draft.active_document_id);
      button.dataset.viewed = String(draft.viewed_document_ids.includes(document.id));
      add(button, "small", "", `${String(index + 1).padStart(2, "0")} · ${document.type}`);
      add(button, "strong", "", document.title);
      button.addEventListener("click", () => openDocument(document.id), { signal });
    });

    const active = documents[activeIndex] || documents[0];
    const reader = add(stage, "article", "lab-reader");
    const readerToolbar = add(reader, "header", "lab-reader-toolbar");
    const previous = add(readerToolbar, "button", "lab-page-button", "← 上一份");
    previous.type = "button";
    previous.disabled = activeIndex <= 0;
    previous.addEventListener("click", () => openDocument(documents[activeIndex - 1]?.id), { signal });
    const pageCounter = add(readerToolbar, "div", "lab-page-counter");
    add(pageCounter, "small", "", active?.location || "证物袋");
    add(pageCounter, "strong", "", `第 ${activeIndex + 1} / ${documents.length} 份`);
    const next = add(readerToolbar, "button", "lab-page-button", "下一份 →");
    next.type = "button";
    next.disabled = activeIndex >= documents.length - 1;
    next.addEventListener("click", () => openDocument(documents[activeIndex + 1]?.id), { signal });

    const paper = add(reader, "div", "lab-paper");
    add(paper, "small", "lab-paper-stamp", active?.type || "待核材料");
    add(paper, "h2", "", active?.title || "卷宗材料");
    add(paper, "p", "lab-paper-body", active?.body || "材料正文等待恢复。");
    add(paper, "p", "lab-paper-footer", active?.footer || "来源等待恢复。");
    const fieldPanel = add(paper, "section", "lab-field-panel");
    add(fieldPanel, "small", "", "荧光笔｜标记真正影响时间、金额、来源与边界的字段");
    const activeFields = fields.filter((item) => item.documentId === active?.id);
    if (!activeFields.length) {
      add(fieldPanel, "p", "lab-field-empty", "本页没有可标记字段，但仍需判断它缺少了什么。");
    }
    activeFields.forEach((field) => {
      const locked = serverAcceptedFields.has(field.id) || acceptedIds.has(field.id);
      const marked = draft.marked_field_ids.includes(field.id);
      const button = add(fieldPanel, "button", "lab-field-option", field.label);
      button.type = "button";
      button.dataset.marked = String(marked);
      button.dataset.locked = String(locked);
      if (rejectedIds.has(field.id)) button.classList.add("is-rejected");
      button.setAttribute("aria-pressed", String(marked));
      button.disabled = locked;
      button.addEventListener("click", () => {
        if (locked) return;
        draft.marked_field_ids = marked
          ? draft.marked_field_ids.filter((id) => id !== field.id)
          : unique([...draft.marked_field_ids, field.id]);
        save();
        renderEvidenceLab(component);
      }, { signal });
    });

    const footer = add(stage, "footer", "lab-action-deck");
    const requiredViews = asInteger(readingTask.required_view_count, documents.length, 1, 12);
    const targetMarks = asInteger(readingTask.target_mark_count, 8, 1, 40);
    const progressCopy = add(footer, "div", "lab-action-progress");
    add(progressCopy, "small", "", "READING TRACE");
    add(
      progressCopy,
      "strong",
      "",
      `已翻阅 ${draft.viewed_document_ids.length}/${requiredViews}｜当前标记 ${draft.marked_field_ids.length}｜已锁定 ${serverAcceptedFields.size}`,
    );
    const submitButton = add(footer, "button", "lab-primary-action", "提交本轮标记 →");
    submitButton.type = "button";
    submitButton.disabled = (
      draft.viewed_document_ids.length < requiredViews ||
      draft.marked_field_ids.length < targetMarks
    );
    submitButton.addEventListener("click", () => submit("submit_reading", {
      viewed_document_ids: draft.viewed_document_ids,
      marked_field_ids: draft.marked_field_ids,
    }), { signal });
    maybeRenderKeepsake(draft.viewed_document_ids.length >= requiredViews);
  };

  const renderClassification = () => {
    stage.classList.add("classification-stage");
    const intro = add(stage, "header", "lab-scene-intro");
    add(intro, "small", "", "REPORTING-DATE AIRLOCK");
    add(intro, "h2", "", "把材料送回它真正属于的时间");
    add(intro, "p", "", "拖拽陈述卡到三座时间舱。正确卡会锁定；放错的只有这一张退回。期后验证不是年末事实，内部信心也不是外部证据。");
    const board = add(stage, "div", "lab-classification-board");
    const rack = add(board, "section", "lab-card-rack");
    add(rack, "small", "", "待归档陈述");
    const unplaced = classificationItems.filter((item) => !draft.placements[item.id]);
    const cards = add(rack, "div", "lab-rack-cards");
    if (!unplaced.length) add(cards, "p", "lab-rack-empty", "所有陈述已进入时间舱，等待核验。");

    const makeItemCard = (item, locked = false) => {
      const card = add(document.createDocumentFragment(), "button", "lab-statement-card");
      card.type = "button";
      card.dataset.itemId = item.id;
      card.dataset.locked = String(locked);
      card.setAttribute("aria-pressed", "false");
      if (rejectedIds.has(item.id)) card.classList.add("is-returned");
      add(card, "span", "", item.label);
      if (locked) add(card, "small", "", "已核验锁定");
      bindDraggable(card, "classification", item.id);
      return card;
    };
    unplaced.forEach((item) => cards.append(makeItemCard(item)));

    const zones = add(board, "section", "lab-time-zones");
    classes.forEach((zone, index) => {
      const zoneNode = add(zones, "section", "lab-time-zone");
      zoneNode.dataset.dropKind = "classification";
      zoneNode.dataset.zoneId = zone.id;
      zoneNode.dataset.zoneIndex = String(index);
      zoneNode.tabIndex = 0;
      const heading = add(zoneNode, "header", "");
      add(heading, "small", "", `TIME VAULT ${String(index + 1).padStart(2, "0")}`);
      add(heading, "strong", "", zone.label);
      const list = add(zoneNode, "div", "lab-zone-cards");
      classificationItems.filter((item) => draft.placements[item.id] === zone.id).forEach((item) => {
        const locked = Object.prototype.hasOwnProperty.call(serverAcceptedPlacements, item.id) || acceptedIds.has(item.id);
        list.append(makeItemCard(item, locked));
      });
      const place = (itemId) => {
        if (!classificationIds.has(itemId) || serverAcceptedPlacements[itemId]) return;
        draft.placements[itemId] = zone.id;
        clearSelected();
        save();
        renderEvidenceLab(component);
      };
      zoneNode.addEventListener("labdrop", (event) => {
        if (event.detail?.kind === "classification") place(event.detail.id);
      }, { signal });
      zoneNode.addEventListener("click", (event) => {
        if (event.target.closest(".lab-statement-card")) return;
        if (selectedCard?.kind === "classification") place(selectedCard.id);
      }, { signal });
      zoneNode.addEventListener("keydown", (event) => {
        if ((event.key === "Enter" || event.key === " ") && selectedCard?.kind === "classification") {
          event.preventDefault();
          place(selectedCard.id);
        }
      }, { signal });
    });

    const footer = add(stage, "footer", "lab-action-deck");
    const acceptedCount = Object.keys(serverAcceptedPlacements).length;
    const progressCopy = add(footer, "div", "lab-action-progress");
    add(progressCopy, "small", "", "BOUNDARY CONTROL");
    add(progressCopy, "strong", "", `已摆放 ${Object.keys(draft.placements).length}/${classificationItems.length}｜已锁定 ${acceptedCount}`);
    const submitButton = add(footer, "button", "lab-primary-action", "核验时间边界 →");
    submitButton.type = "button";
    submitButton.disabled = Object.keys(draft.placements).length < classificationItems.length;
    submitButton.addEventListener("click", () => submit("submit_classification", {
      placements: draft.placements,
    }), { signal });
    maybeRenderKeepsake(acceptedCount >= 2 || Object.keys(draft.placements).length === classificationItems.length);
  };

  const renderChain = () => {
    stage.classList.add("chain-stage");
    const intro = add(stage, "header", "lab-scene-intro");
    add(intro, "small", "", "EVIDENCE ARCHITECTURE TABLE");
    add(intro, "h2", "", "让每条主张找到能直接回答它的来源");
    add(intro, "p", "", "拖拽一份来源到研究主张，或先点来源、再点主张。正确连线会锁定；错误连线只会断开自己。");
    const board = add(stage, "div", "lab-chain-board");
    const svg = add(board, "svg", "lab-chain-lines");
    svg.setAttribute("aria-hidden", "true");
    const sourceNodes = new Map();
    const claimNodes = new Map();
    const sources = add(board, "section", "lab-source-bank");
    add(sources, "small", "", "SOURCE FILES · 来源材料");
    documents.forEach((document) => {
      const card = add(sources, "button", "lab-source-card");
      card.type = "button";
      card.dataset.sourceId = document.id;
      card.dataset.locked = "false";
      card.setAttribute("aria-pressed", "false");
      sourceNodes.set(document.id, card);
      add(card, "small", "", document.type);
      add(card, "strong", "", document.title);
      bindDraggable(card, "source", document.id);
    });
    const claimPanel = add(board, "section", "lab-claim-bank");
    add(claimPanel, "small", "", "RESEARCH CLAIMS · 待证明主张");
    claims.forEach((claim, index) => {
      const claimNode = add(claimPanel, "article", "lab-claim-node");
      claimNode.dataset.dropKind = "source";
      claimNode.dataset.claimId = claim.id;
      claimNode.tabIndex = 0;
      const locked = Object.prototype.hasOwnProperty.call(serverAcceptedLinks, claim.id) || acceptedIds.has(claim.id);
      claimNode.dataset.locked = String(locked);
      if (rejectedIds.has(claim.id)) claimNode.classList.add("is-rejected");
      claimNodes.set(claim.id, claimNode);
      add(claimNode, "small", "", `CLAIM ${String(index + 1).padStart(2, "0")}`);
      add(claimNode, "strong", "", claim.label);
      const linkedId = draft.links[claim.id];
      const linkedDocument = documents.find((item) => item.id === linkedId);
      add(
        claimNode,
        "span",
        "lab-linked-source",
        linkedDocument ? `${locked ? "已锁定" : "待核验"}｜${linkedDocument.title}` : "拖入一份直接来源",
      );
      const connect = (sourceId) => {
        if (locked || !documentIds.has(sourceId)) return;
        draft.links[claim.id] = sourceId;
        clearSelected();
        save();
        renderEvidenceLab(component);
      };
      claimNode.addEventListener("labdrop", (event) => {
        if (event.detail?.kind === "source") connect(event.detail.id);
      }, { signal });
      claimNode.addEventListener("click", () => {
        if (selectedCard?.kind === "source") connect(selectedCard.id);
      }, { signal });
      claimNode.addEventListener("keydown", (event) => {
        if ((event.key === "Enter" || event.key === " ") && selectedCard?.kind === "source") {
          event.preventDefault();
          connect(selectedCard.id);
        }
      }, { signal });
    });

    const drawLines = () => {
      svg.replaceChildren();
      const boardRect = board.getBoundingClientRect();
      Object.entries(draft.links).forEach(([claimId, sourceId]) => {
        const source = sourceNodes.get(sourceId);
        const claim = claimNodes.get(claimId);
        if (!source || !claim) return;
        const sourceRect = source.getBoundingClientRect();
        const claimRect = claim.getBoundingClientRect();
        const x1 = sourceRect.right - boardRect.left;
        const y1 = sourceRect.top + sourceRect.height / 2 - boardRect.top;
        const x2 = claimRect.left - boardRect.left;
        const y2 = claimRect.top + claimRect.height / 2 - boardRect.top;
        const curve = Math.max(40, (x2 - x1) * 0.42);
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", `M ${x1} ${y1} C ${x1 + curve} ${y1}, ${x2 - curve} ${y2}, ${x2} ${y2}`);
        path.dataset.locked = String(Object.prototype.hasOwnProperty.call(serverAcceptedLinks, claimId) || acceptedIds.has(claimId));
        svg.append(path);
      });
    };
    requestAnimationFrame(drawLines);
    if (globalThis.ResizeObserver) {
      resizeObserver = new ResizeObserver(drawLines);
      resizeObserver.observe(board);
    }

    const footer = add(stage, "footer", "lab-action-deck");
    const acceptedCount = Object.keys(serverAcceptedLinks).length;
    const progressCopy = add(footer, "div", "lab-action-progress");
    add(progressCopy, "small", "", "CHAIN INTEGRITY");
    add(progressCopy, "strong", "", `已连线 ${Object.keys(draft.links).length}/${claims.length}｜已锁定 ${acceptedCount}`);
    const submitButton = add(footer, "button", "lab-primary-action", "检验四环证据链 →");
    submitButton.type = "button";
    submitButton.disabled = Object.keys(draft.links).length < claims.length;
    submitButton.addEventListener("click", () => submit("submit_chain", {
      links: draft.links,
    }), { signal });
    maybeRenderKeepsake(acceptedCount >= 2 || Object.keys(draft.links).length === claims.length);
  };

  if (phase === "reading") renderReading();
  else if (phase === "classification") renderClassification();
  else renderChain();

  const footerNote = add(shell, "footer", "lab-footer-note");
  footerNote.textContent = "只把材料放进正确位置还不够：先问它发生在何时，再问它真正证明了什么。";
  shell.append(announce);

  root.__evidenceLabCleanup?.();
  root.replaceChildren(shell);
  root.__evidenceLabCleanup = () => {
    resizeObserver?.disconnect();
    dragGhost?.remove();
    controller.abort();
  };

  return () => {
    root.__evidenceLabCleanup?.();
    root.__evidenceLabCleanup = undefined;
  };
}
