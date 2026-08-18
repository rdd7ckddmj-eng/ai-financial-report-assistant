const SCHEMA_VERSION = 1;
const SUBMIT_ACTION = "submit_committee_statement";
const SEAT_IDS = ["conclusion_strength", "evidence_boundary", "next_action"];
const UI_ACTIONS = new Set([
  "go_back",
  "rename_player",
  "restart_game",
  "exit_game",
  "discover_keepsake",
]);

const asObject = (value) => (
  value && typeof value === "object" && !Array.isArray(value) ? value : {}
);
const asList = (value) => (Array.isArray(value) ? value : []);
const asText = (value, fallback = "", max = 320) => {
  if (typeof value !== "string" && typeof value !== "number") return fallback;
  const clean = String(value).trim();
  return clean ? clean.slice(0, max) : fallback;
};
const asInteger = (value, fallback = 0, min = 0, max = 999) => {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(number)));
};
const add = (parent, tag, className = "", text = "") => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== "") node.textContent = String(text);
  parent.append(node);
  return node;
};
const unique = (items) => [...new Set(items)];

const makeCommandId = () => {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `committee-${Date.now()}-${Math.random().toString(16).slice(2, 12)}`;
};

const cleanSeat = (raw, index) => {
  const item = asObject(raw);
  const seatId = asText(item.seat_id, SEAT_IDS[index] || "", 60);
  const cards = asList(item.cards).slice(0, 8).map((rawCard, cardIndex) => {
    const card = asObject(rawCard);
    return {
      id: asText(card.card_id, `${seatId}:card:${cardIndex + 1}`, 90),
      text: asText(card.text, `答辩陈述 ${cardIndex + 1}`, 620),
    };
  });
  return {
    id: seatId,
    title: asText(item.title, `审查席 ${index + 1}`, 70),
    examiner: asText(item.examiner, `审查官 ${index + 1}`, 90),
    instruction: asText(item.instruction, "只陈述证据能够支持的范围。", 180),
    prompt: asText(item.prompt, "请向本席提交一枚答辩牌。", 260),
    cards,
  };
};

const cleanPlacements = (raw, cardsBySeat) => {
  const placements = {};
  Object.entries(asObject(raw)).forEach(([seatId, cardId]) => {
    if (!SEAT_IDS.includes(seatId) || typeof cardId !== "string") return;
    if (cardsBySeat.get(seatId)?.has(cardId)) placements[seatId] = cardId;
  });
  return placements;
};

const cleanSeatIds = (raw) => unique(
  asList(raw).filter((item) => typeof item === "string" && SEAT_IDS.includes(item)),
);

const safeLoadDraft = (storageKey) => {
  try {
    const encoded = globalThis.localStorage?.getItem(storageKey);
    if (!encoded || encoded.length > 12000) return {};
    return asObject(JSON.parse(encoded));
  } catch {
    return {};
  }
};

const safeSaveDraft = (storageKey, draft) => {
  try {
    globalThis.localStorage?.setItem(storageKey, JSON.stringify(draft));
  } catch {
    // A blocked/private localStorage must never prevent a formal hearing.
  }
};

const normalisePassedRounds = (state) => {
  const explicit = asList(state.passed_round_numbers);
  const fallback = explicit.length ? explicit : asList(state.passed_rounds);
  const numeric = fallback
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value));
  const zeroBased = numeric.includes(0);
  return new Set(
    numeric
      .map((value) => zeroBased ? value + 1 : value)
      .filter((value) => value >= 1 && value <= 3),
  );
};

const scenarioCopy = (scenarioType) => ({
  explained_timing_gap: ["时点差异", "利润与现金走在两只钟上"],
  late_acceptance: ["跨期验收", "期后发生不能倒流成年末事实"],
  overdue_uncollected: ["逾期未收", "收入存在与应收可收回性必须分开"],
  partial_acceptance: ["部分履约", "完成比例必须由可追溯证据承担"],
}[scenarioType] || ["动态审查", "只让证据承担它真正知道的部分"]);

const seatVisualDefaults = {
  conclusion_strength: {
    image: "/app/static/cash-game-mentor-08.png",
    badge: "01",
    short: "结论",
    color: "blue",
  },
  evidence_boundary: {
    image: "/app/static/cash-game-mentor-06.png",
    badge: "02",
    short: "边界",
    color: "cyan",
  },
  next_action: {
    image: "/app/static/cash-game-mentor-09.png",
    badge: "03",
    short: "行动",
    color: "gold",
  },
};

const portraitForSeat = (state, seat) => {
  const override = asObject(asObject(state.npc_by_seat)[seat.id]);
  const defaults = seatVisualDefaults[seat.id];
  return {
    ...defaults,
    image: asText(override.image_url, defaults.image, 420),
    name: asText(override.name, seat.examiner.split("｜")[0], 40),
    role: asText(override.role, seat.examiner.split("｜")[1] || seat.title, 70),
    line: asText(override.line, seat.instruction, 180),
  };
};

export default function renderDefenseCommittee(component) {
  const { data, parentElement, setTriggerValue } = component;
  const root = parentElement.querySelector(".committee-game");
  if (!root) return undefined;

  const payload = asObject(data);
  const state = asObject(payload.state);
  const task = asObject(state.task);
  const taskId = asText(payload.task_id, asText(task.task_id, "", 160), 160);
  const revision = asInteger(payload.revision, 0, 0, 1e7);
  const storageKey = asText(
    payload.draft_storage_key,
    "wfz_cash_defense_committee_draft",
    180,
  );
  const seats = asList(task.seats)
    .slice(0, 3)
    .map(cleanSeat)
    .filter((seat) => SEAT_IDS.includes(seat.id));
  const seatById = new Map(seats.map((seat) => [seat.id, seat]));
  const cardsBySeat = new Map(
    seats.map((seat) => [seat.id, new Set(seat.cards.map((card) => card.id))]),
  );
  const roundNumber = asInteger(task.round_number, 1, 1, 3);
  const challengeNumber = asInteger(task.challenge_number, 1, 1, 999);
  const passedRounds = normalisePassedRounds(state);
  const progress = asObject(state.progress);
  const evaluation = asObject(state.evaluation);
  const evaluationTaskId = asText(
    state.evaluation_task_id || evaluation.task_id,
    "",
    160,
  );
  const evaluationMatchesTask = evaluationTaskId === taskId;
  const acknowledgedId = asText(state.acknowledged_command_id, "", 120);
  const acceptedSeats = new Set(
    evaluationMatchesTask ? cleanSeatIds(evaluation.accepted) : [],
  );
  const rejectedSeats = new Set(
    evaluationMatchesTask ? cleanSeatIds(evaluation.rejected) : [],
  );
  const submittedPlacements = cleanPlacements(
    asObject(evaluation.clean_payload).placements,
    cardsBySeat,
  );
  const serverPlacements = cleanPlacements(
    progress.accepted_placements || state.accepted_placements,
    cardsBySeat,
  );

  const emptyDraft = {
    version: 1,
    task_id: taskId,
    revision,
    active_seat_id: SEAT_IDS.find((id) => seatById.has(id)) || "",
    visited_seat_ids: [],
    placements: {},
    applied_ack_id: "",
  };
  const stored = safeLoadDraft(storageKey);
  let draft = (
    stored.version === 1 &&
    stored.task_id === taskId &&
    stored.revision === revision
  ) ? { ...emptyDraft, ...stored } : emptyDraft;
  draft.placements = cleanPlacements(draft.placements, cardsBySeat);
  draft.active_seat_id = seatById.has(draft.active_seat_id)
    ? draft.active_seat_id
    : emptyDraft.active_seat_id;
  draft.visited_seat_ids = cleanSeatIds(draft.visited_seat_ids);
  if (
    draft.active_seat_id &&
    !draft.visited_seat_ids.includes(draft.active_seat_id)
  ) {
    draft.visited_seat_ids.push(draft.active_seat_id);
  }

  if (
    evaluationMatchesTask && acknowledgedId &&
    draft.applied_ack_id !== acknowledgedId
  ) {
    acceptedSeats.forEach((seatId) => {
      if (submittedPlacements[seatId]) {
        draft.placements[seatId] = submittedPlacements[seatId];
      }
    });
    rejectedSeats.forEach((seatId) => delete draft.placements[seatId]);
    draft.applied_ack_id = acknowledgedId;
  }
  Object.assign(draft.placements, serverPlacements);
  const lockedPlacements = { ...serverPlacements };
  if (evaluationMatchesTask) {
    acceptedSeats.forEach((seatId) => {
      if (submittedPlacements[seatId]) {
        lockedPlacements[seatId] = submittedPlacements[seatId];
      }
    });
  }
  safeSaveDraft(storageKey, draft);

  const controller = new AbortController();
  const { signal } = controller;
  let pending = false;
  let selectedCard = null;
  let drag = null;
  let dragGhost = null;

  const shell = document.createElement("section");
  shell.className = `committee-shell round-${roundNumber}`;
  shell.dataset.scenario = asText(task.scenario_type, "dynamic", 60);
  const liveRegion = add(shell, "div", "committee-live-region");
  liveRegion.setAttribute("role", "status");
  liveRegion.setAttribute("aria-live", "polite");

  const save = () => safeSaveDraft(storageKey, draft);
  const sendCommand = (action, extra = null) => {
    if (pending || (!UI_ACTIONS.has(action) && action !== SUBMIT_ACTION)) return;
    pending = true;
    shell.classList.add("is-pending");
    liveRegion.textContent = action === SUBMIT_ACTION
      ? "答辩陈述已经送入委员会终端"
      : "正在执行界面操作";
    const command = {
      schema_version: SCHEMA_VERSION,
      command_id: makeCommandId(),
      task_id: taskId,
      revision,
      action,
    };
    if (action === SUBMIT_ACTION) command.placements = { ...extra };
    setTriggerValue("command", command);
  };

  const header = add(shell, "header", "committee-hud");
  const brand = add(header, "div", "committee-brand");
  add(brand, "small", "", "FANGZHENG AI · REVIEW CHAMBER");
  add(brand, "strong", "", "《消失的现金》");

  const rounds = add(header, "nav", "committee-rounds");
  rounds.setAttribute("aria-label", "委员会三轮进度");
  [1, 2, 3].forEach((number) => {
    const item = add(rounds, "div", "committee-round-marker");
    item.dataset.status = passedRounds.has(number)
      ? "passed"
      : number === roundNumber ? "current" : "locked";
    add(item, "b", "", passedRounds.has(number) ? "✓" : String(number));
    add(item, "span", "", number === 1 ? "初审" : number === 2 ? "复核" : "终审");
  });

  const identity = add(header, "div", "committee-identity");
  add(identity, "small", "", "调查员");
  add(identity, "strong", "", asText(state.player_name, "见习研究员", 40));

  const lives = asInteger(state.lives, 3, 0, 3);
  const maxLives = asInteger(state.max_lives, 3, 1, 3);
  const lifePanel = add(header, "div", "committee-lives");
  lifePanel.setAttribute("aria-label", `剩余 ${lives} 次正式容错`);
  add(lifePanel, "small", "", "正式容错");
  const hearts = add(lifePanel, "div", "committee-hearts");
  for (let index = 0; index < maxLives; index += 1) {
    const heart = add(hearts, "span", "", "♥");
    heart.dataset.live = String(index < lives);
  }

  const toolbar = add(header, "nav", "committee-toolbar");
  toolbar.setAttribute("aria-label", "案件操作");
  [
    ["go_back", "←", "上一步"],
    ["rename_player", "名", "修改代号"],
    ["restart_game", "↻", "重新开始"],
    ["exit_game", "⌂", "退出案件"],
  ].forEach(([action, icon, label]) => {
    const button = add(toolbar, "button", "committee-toolbar-button");
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    add(button, "b", "", icon);
    add(button, "span", "", label);
    button.addEventListener("click", () => sendCommand(action), { signal });
  });

  const room = add(shell, "main", "committee-room");

  if (roundNumber === 3) {
    const gallery = add(room, "div", "committee-council-gallery");
    gallery.setAttribute("aria-hidden", "true");
    for (let number = 1; number <= 9; number += 1) {
      const card = add(gallery, "div", "committee-gallery-card");
      const image = add(card, "img");
      image.src = `/app/static/cash-game-mentor-${String(number).padStart(2, "0")}.png`;
      image.alt = "";
      add(card, "span", "", String(number).padStart(2, "0"));
    }
  }

  const dossier = add(room, "aside", "committee-dossier");
  const [scenarioLabel, scenarioLine] = scenarioCopy(
    asText(task.scenario_type, "dynamic", 60),
  );
  const dossierHead = add(dossier, "header", "committee-dossier-head");
  const fileNumber = add(dossierHead, "div", "committee-file-number");
  add(fileNumber, "small", "", `ROUND ${String(roundNumber).padStart(2, "0")}`);
  add(fileNumber, "strong", "", `动态卷 ${String(challengeNumber).padStart(2, "0")}`);
  const scenario = add(dossierHead, "div", "committee-scenario");
  add(scenario, "small", "", scenarioLabel);
  add(scenario, "strong", "", asText(task.company_name, "待审公司", 80));
  add(dossier, "p", "committee-scenario-line", scenarioLine);
  const evidenceList = add(dossier, "ol", "committee-evidence-list");
  asList(task.evidence_items).slice(0, 6).forEach((item, index) => {
    const evidence = add(evidenceList, "li", "committee-evidence-item");
    add(evidence, "b", "", String(index + 1).padStart(2, "0"));
    add(evidence, "span", "", asText(item, "证据内容等待恢复。", 360));
  });
  const rule = add(dossier, "footer", "committee-rule");
  add(rule, "b", "", "审查规则");
  add(rule, "span", "", asText(
    task.committee_rule,
    "三席各放一枚答辩牌；正式错误才消耗容错。",
    260,
  ));

  const chamber = add(room, "section", "committee-chamber");
  const chamberTitle = add(chamber, "header", "committee-chamber-title");
  add(chamberTitle, "small", "", `HEARING ${roundNumber} / 3`);
  add(chamberTitle, "h2", "", roundNumber === 3
    ? "九席旁听，三席签字"
    : roundNumber === 2 ? "交换立场，再审一次边界" : "让三句话组成一份研究意见");
  const feedbackState = asObject(state.feedback);
  const feedbackMessage = asText(
    evaluation.feedback || feedbackState.message,
    "先点答辩牌、再点席位也能操作；已获认可的席位会由服务端锁定。",
    500,
  );
  add(chamberTitle, "p", "", feedbackMessage);

  const seatDeck = add(chamber, "div", "committee-seat-deck");
  let activeSeatId = draft.active_seat_id;

  const keepsakeDiscovered = state.keepsake_discovered === true;
  const allSeatsObserved = SEAT_IDS.every(
    (seatId) => draft.visited_seat_ids.includes(seatId),
  );
  if (keepsakeDiscovered) {
    const inventory = add(chamberTitle, "div", "committee-keepsake-owned");
    inventory.setAttribute("aria-label", "物品栏：逆向黑棋");
    add(inventory, "b", "", "◆");
    add(inventory, "span", "", `物品栏｜${asText(state.keepsake_name, "逆向黑棋", 40)}`);
  } else if (allSeatsObserved) {
    const keepsake = add(chamberTitle, "button", "committee-keepsake-clue");
    keepsake.type = "button";
    keepsake.title = "委员会封蜡边缘压着一枚不属于徽记的黑色棋子";
    keepsake.setAttribute("aria-label", "检查委员会封蜡下的异常黑色棋子");
    add(keepsake, "i", "", "◆");
    add(keepsake, "span", "", "封蜡暗纹");
    keepsake.addEventListener(
      "click",
      () => sendCommand("discover_keepsake"),
      { signal },
    );
  }

  const cardForPlacement = (seatId) => {
    const cardId = draft.placements[seatId];
    return seatById.get(seatId)?.cards.find((card) => card.id === cardId) || null;
  };

  const setActiveSeat = (seatId) => {
    if (!seatById.has(seatId)) return;
    draft.active_seat_id = seatId;
    draft.visited_seat_ids = unique([
      ...draft.visited_seat_ids,
      seatId,
    ]);
    save();
    renderDefenseCommittee(component);
  };

  const setSelectedCard = (seatId, cardId, cardNode) => {
    shell.querySelectorAll(".is-selected-card").forEach((node) => {
      node.classList.remove("is-selected-card");
      node.setAttribute("aria-pressed", "false");
    });
    selectedCard = { seatId, cardId };
    cardNode.classList.add("is-selected-card");
    cardNode.setAttribute("aria-pressed", "true");
    liveRegion.textContent = "答辩牌已拿起，请选择对应审查席";
  };

  const placeCard = (seatId, cardId) => {
    if (lockedPlacements[seatId]) return;
    if (!cardsBySeat.get(seatId)?.has(cardId)) {
      const target = shell.querySelector(`[data-seat-id="${seatId}"]`);
      target?.classList.add("is-refusing-card");
      globalThis.setTimeout(() => target?.classList.remove("is-refusing-card"), 480);
      liveRegion.textContent = "这枚牌属于另一位审查官，请先辨认席位任务";
      return;
    }
    draft.placements[seatId] = cardId;
    draft.active_seat_id = SEAT_IDS.find(
      (candidate) => seatById.has(candidate) && !draft.placements[candidate],
    ) || seatId;
    selectedCard = null;
    save();
    renderDefenseCommittee(component);
  };

  seats.forEach((seat) => {
    const visual = portraitForSeat(state, seat);
    const seatNode = add(seatDeck, "article", `committee-seat tone-${visual.color}`);
    seatNode.dataset.seatId = seat.id;
    seatNode.dataset.active = String(seat.id === activeSeatId);
    seatNode.dataset.locked = String(Boolean(lockedPlacements[seat.id]));
    seatNode.dataset.rejected = String(rejectedSeats.has(seat.id));
    seatNode.tabIndex = 0;
    seatNode.setAttribute("role", "button");
    seatNode.setAttribute("aria-label", `${seat.title}，${seat.examiner}`);

    const portrait = add(seatNode, "div", "committee-seat-portrait");
    const image = add(portrait, "img");
    image.src = visual.image;
    image.alt = `${visual.name}，${visual.role}`;
    add(portrait, "span", "", visual.badge);
    const copy = add(seatNode, "div", "committee-seat-copy");
    add(copy, "small", "", visual.role);
    add(copy, "strong", "", visual.name);
    add(copy, "p", "", visual.line);
    const plaque = add(seatNode, "div", "committee-seat-plaque");
    add(plaque, "b", "", seat.title);
    add(plaque, "span", "", seat.prompt);

    const dock = add(seatNode, "div", "committee-answer-dock");
    dock.dataset.dropSeat = seat.id;
    const placedCard = cardForPlacement(seat.id);
    if (placedCard) {
      dock.dataset.filled = "true";
      add(dock, "small", "", lockedPlacements[seat.id] ? "委员会已锁定" : "待正式核验");
      const answer = add(dock, "button", "committee-placed-card", placedCard.text);
      answer.type = "button";
      answer.title = placedCard.text;
      answer.disabled = Boolean(lockedPlacements[seat.id]);
      answer.addEventListener("click", (event) => {
        event.stopPropagation();
        if (!lockedPlacements[seat.id]) {
          delete draft.placements[seat.id];
          save();
          renderDefenseCommittee(component);
        }
      }, { signal });
    } else {
      dock.dataset.filled = "false";
      add(dock, "b", "", "+");
      add(dock, "span", "", `将“${visual.short}”答辩牌放在这里`);
    }

    const acceptSelected = () => {
      if (selectedCard) placeCard(seat.id, selectedCard.cardId);
      else setActiveSeat(seat.id);
    };
    seatNode.addEventListener("committee-drop", (event) => {
      placeCard(seat.id, event.detail?.cardId || "");
    }, { signal });
    seatNode.addEventListener("click", acceptSelected, { signal });
    seatNode.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        acceptSelected();
      }
    }, { signal });
  });

  const tray = add(chamber, "section", "committee-card-tray");
  const tabs = add(tray, "nav", "committee-seat-tabs");
  tabs.setAttribute("aria-label", "切换答辩牌组");
  seats.forEach((seat) => {
    const tab = add(tabs, "button", "committee-seat-tab");
    tab.type = "button";
    tab.dataset.active = String(seat.id === activeSeatId);
    tab.dataset.filled = String(Boolean(draft.placements[seat.id]));
    add(tab, "b", "", seatVisualDefaults[seat.id].badge);
    add(tab, "span", "", seat.title.replace("席", ""));
    if (lockedPlacements[seat.id]) add(tab, "em", "", "已锁定");
    else if (draft.placements[seat.id]) add(tab, "em", "", "待核验");
    tab.addEventListener("click", () => setActiveSeat(seat.id), { signal });
  });

  const activeSeat = seatById.get(activeSeatId) || seats[0];
  const cards = add(tray, "div", "committee-card-rack");
  if (activeSeat) {
    activeSeat.cards.forEach((card, index) => {
      const usedHere = draft.placements[activeSeat.id] === card.id;
      const cardNode = add(cards, "button", "committee-statement-card");
      cardNode.type = "button";
      cardNode.dataset.cardId = card.id;
      cardNode.dataset.seatId = activeSeat.id;
      cardNode.dataset.used = String(usedHere);
      cardNode.setAttribute("aria-pressed", "false");
      cardNode.setAttribute("aria-label", `答辩牌 ${index + 1}：${card.text}`);
      add(cardNode, "small", "", `STATEMENT ${String(index + 1).padStart(2, "0")}`);
      add(cardNode, "span", "", card.text);
      if (usedHere) {
        add(cardNode, "b", "", lockedPlacements[activeSeat.id] ? "已锁定" : "已上席");
        cardNode.disabled = true;
      } else if (!lockedPlacements[activeSeat.id]) {
        cardNode.addEventListener("click", () => {
          setSelectedCard(activeSeat.id, card.id, cardNode);
        }, { signal });
        cardNode.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setSelectedCard(activeSeat.id, card.id, cardNode);
          }
        }, { signal });
        cardNode.addEventListener("pointerdown", (event) => {
          if (event.button !== 0) return;
          drag = {
            pointerId: event.pointerId,
            cardId: card.id,
            seatId: activeSeat.id,
            source: cardNode,
            x: event.clientX,
            y: event.clientY,
            moved: false,
          };
          cardNode.setPointerCapture?.(event.pointerId);
        }, { signal });
      }
    });
  }

  const actions = add(chamber, "footer", "committee-actions");
  const actionCopy = add(actions, "div", "committee-action-copy");
  const placedCount = Object.keys(draft.placements).length;
  add(actionCopy, "small", "", "RESEARCH STATEMENT");
  add(actionCopy, "strong", "", `${placedCount} / 3 席已经收到答辩牌`);
  add(actionCopy, "span", "", placedCount < 3
    ? "空席提交不会扣生命；完整陈述需要结论、边界与行动。"
    : "三句话已经闭合。现在提交的是判断，不是猜测。"
  );
  const submitButton = add(actions, "button", "committee-submit");
  submitButton.type = "button";
  submitButton.disabled = placedCount === 0 || lives <= 0;
  add(submitButton, "span", "", placedCount === 3 ? "提交完整答辩" : "提交当前席位");
  add(submitButton, "b", "", "→");
  submitButton.addEventListener("click", () => {
    sendCommand(SUBMIT_ACTION, draft.placements);
  }, { signal });

  const feedback = add(dossier, "aside", "committee-feedback");
  feedback.dataset.tone = asText(
    feedbackState.tone,
    rejectedSeats.size ? "warning" : evaluation.complete ? "success" : "info",
    20,
  );
  add(feedback, "small", "", "审查终端 · 实时回执");
  add(feedback, "strong", "", asText(
    feedbackState.title,
    evaluation.complete ? "三席一致通过" : rejectedSeats.size ? "当前挑战已更换" : "委员会正在等你的陈述",
    100,
  ));
  add(feedback, "p", "", asText(
    evaluation.feedback || feedbackState.message,
    "错牌只退回当前挑战；已通过的轮次不会被抹去。",
    500,
  ));

  const footer = add(shell, "footer", "committee-footer-note");
  footer.textContent = "结论要有强度，证据要有边界，行动要能改变判断。三者缺一，研究意见就只是语气。";

  const moveDrag = (event) => {
    if (!drag || drag.pointerId !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - drag.x, event.clientY - drag.y);
    if (!drag.moved && distance < 7) return;
    drag.moved = true;
    event.preventDefault();
    if (!dragGhost) {
      dragGhost = add(shell, "div", "committee-drag-ghost", drag.source.textContent || "答辩牌");
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
    current.source.releasePointerCapture?.(event.pointerId);
    if (!current.moved) return;
    const target = document
      .elementFromPoint(event.clientX, event.clientY)
      ?.closest("[data-seat-id]");
    if (target) {
      target.dispatchEvent(new CustomEvent("committee-drop", {
        bubbles: true,
        detail: { cardId: current.cardId, seatId: current.seatId },
      }));
    } else {
      liveRegion.textContent = "答辩牌没有落在审查席上，已回到牌架";
    }
  };
  document.addEventListener("pointermove", moveDrag, { signal, passive: false });
  document.addEventListener("pointerup", finishDrag, { signal });
  document.addEventListener("pointercancel", finishDrag, { signal });

  root.__committeeCleanup?.();
  root.replaceChildren(shell);
  root.__committeeCleanup = () => {
    dragGhost?.remove();
    controller.abort();
  };

  return () => {
    root.__committeeCleanup?.();
    root.__committeeCleanup = undefined;
  };
}
