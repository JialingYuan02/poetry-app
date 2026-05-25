// ── Auth state ────────────────────────────────────────────────────────────────
let authToken    = localStorage.getItem("shiju_token");
let authUsername = localStorage.getItem("shiju_username");
let authIsLogin  = true; // toggle between login / register

function authHeaders() {
  return authToken ? { "Authorization": `Bearer ${authToken}` } : {};
}

async function apiFetch(url, options = {}) {
  options.headers = { ...authHeaders(), ...(options.headers || {}) };
  const resp = await fetch(url, options);
  if (resp.status === 401) {
    _logout();
    showPhase("phase-auth");
    throw new Error("登录已过期，请重新登录");
  }
  return resp;
}

function _logout() {
  authToken = null;
  authUsername = null;
  localStorage.removeItem("shiju_token");
  localStorage.removeItem("shiju_username");
}

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  selectedFile: null,
  matchResult: null,
  currentPoemIdx: 0,
  editEntryId: null,
  uploadDate: todayISO(),
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth() + 1,
  calEntries: [],
  selectedDay: null,
  dayEntries: [],
  dayEntryIdx: 0,
  _pendingOnboarding: false,
};

const CN_MONTHS = [
  '一月','二月','三月','四月','五月','六月',
  '七月','八月','九月','十月','十一月','十二月',
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// ── DOM refs ──────────────────────────────────────────────────────────────────
const bgImage        = document.getElementById("bg-image");
const bgOverlay      = document.getElementById("bg-overlay");
const photoInput     = document.getElementById("photo-input");
const uploadZone     = document.getElementById("upload-zone");
const uploadInner    = document.getElementById("upload-inner");
const moodInput      = document.getElementById("mood-input");
const dateInput      = document.getElementById("date-input");
const matchBtn       = document.getElementById("match-btn");
const analysisTags   = document.getElementById("analysis-tags");
const cardCounter    = document.getElementById("card-counter");
const cardsViewport  = document.getElementById("cards-viewport");
const cardDots       = document.getElementById("card-dots");
const prevBtn        = document.getElementById("prev-btn");
const nextBtn        = document.getElementById("next-btn");
const confirmBtn     = document.getElementById("confirm-btn");
const resetBtn       = document.getElementById("reset-btn");
const calTitle       = document.getElementById("cal-title");
const calGrid        = document.getElementById("cal-grid");
const calPanel       = document.getElementById("cal-panel");
const calPanelInner  = document.getElementById("cal-panel-inner");
const phaseCalendar  = document.getElementById("phase-calendar");
const poemsList      = document.getElementById("poems-list");
const poemsTitle     = document.getElementById("poems-title");

// ── Phase management ──────────────────────────────────────────────────────────
const NO_PHOTO_PHASES = new Set(["phase-auth", "phase-landing", "phase-upload", "phase-calendar", "phase-poems"]);

function showPhase(id) {
  document.querySelectorAll(".phase").forEach(el => el.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  bgOverlay.classList.toggle("dim", NO_PHOTO_PHASES.has(id));

  if (id === "phase-upload" && state._pendingOnboarding) {
    state._pendingOnboarding = false;
    setTimeout(startOnboarding, 320);
  }
}

function clearBg() {
  bgImage.classList.remove("visible", "blurred");
  bgImage.style.backgroundImage = "";
}

function setPhotoBg(photoPath, blurred = false) {
  const url = photoPath.startsWith("blob:") ? photoPath : `/photo/${photoPath}`;
  bgImage.style.backgroundImage = `url(${url})`;
  bgImage.classList.add("visible");
  bgImage.classList.toggle("blurred", blurred);
}

// ── Auth ──────────────────────────────────────────────────────────────────────
const authUsernameEl  = document.getElementById("auth-username");
const authPasswordEl  = document.getElementById("auth-password");
const authErrorEl     = document.getElementById("auth-error");
const authSubmitBtn   = document.getElementById("auth-submit-btn");
const authToggleBtn   = document.getElementById("auth-toggle-btn");

function setAuthMode(isLogin) {
  authIsLogin = isLogin;
  authSubmitBtn.textContent = isLogin ? "登录" : "注册";
  authToggleBtn.textContent = isLogin ? "还没有账号？注册" : "已有账号？登录";
  authErrorEl.textContent = "";
}

authToggleBtn.addEventListener("click", () => setAuthMode(!authIsLogin));

authSubmitBtn.addEventListener("click", async () => {
  const username = authUsernameEl.value.trim();
  const password = authPasswordEl.value;
  authErrorEl.textContent = "";

  if (!username || !password) {
    authErrorEl.textContent = "请填写用户名和密码";
    return;
  }

  authSubmitBtn.disabled = true;
  authSubmitBtn.textContent = authIsLogin ? "登录中…" : "注册中…";

  try {
    const endpoint = authIsLogin ? "/auth/login" : "/auth/register";
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      authErrorEl.textContent = data.detail || (authIsLogin ? "登录失败" : "注册失败");
      return;
    }
    authToken    = data.token;
    authUsername = data.username;
    localStorage.setItem("shiju_token", authToken);
    localStorage.setItem("shiju_username", authUsername);

    document.getElementById("landing-username").textContent = authUsername;
    if (!authIsLogin) {
      state._pendingOnboarding = true;
    }
    showPhase("phase-landing");
  } catch {
    authErrorEl.textContent = "网络错误，请重试";
  } finally {
    authSubmitBtn.disabled = false;
    setAuthMode(authIsLogin);
  }
});

// Allow submitting with Enter key
authPasswordEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") authSubmitBtn.click();
});
authUsernameEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") authPasswordEl.focus();
});

// ── Landing ───────────────────────────────────────────────────────────────────
document.getElementById("landing-logout-btn").addEventListener("click", () => {
  _logout();
  authUsernameEl.value = "";
  authPasswordEl.value = "";
  authErrorEl.textContent = "";
  setAuthMode(true);
  clearBg();
  showPhase("phase-auth");
});

document.getElementById("enter-btn").addEventListener("click", () => {
  state.uploadDate = todayISO();
  dateInput.value = state.uploadDate;
  showPhase("phase-upload");
});

document.getElementById("landing-cal-btn").addEventListener("click", async () => {
  clearBg();
  await loadCalendar();
  showPhase("phase-calendar");
});

document.getElementById("upload-home-btn").addEventListener("click", () => {
  resetUpload();
  clearBg();
  showPhase("phase-landing");
});

document.getElementById("cal-home-btn").addEventListener("click", () => {
  closePanel();
  clearBg();
  showPhase("phase-landing");
});

// ── Upload ────────────────────────────────────────────────────────────────────
dateInput.max = todayISO();
dateInput.value = todayISO();

photoInput.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  state.selectedFile = file;
  const url = URL.createObjectURL(file);
  setPhotoBg(url);
  uploadInner.innerHTML = `<img src="${url}" alt="preview">`;
  matchBtn.disabled = false;
});

dateInput.addEventListener("change", () => {
  state.uploadDate = dateInput.value || todayISO();
});

matchBtn.addEventListener("click", async () => {
  if (!state.selectedFile) return;
  showPhase("phase-loading");
  bgImage.classList.add("blurred");

  const formData = new FormData();
  formData.append("photo", state.selectedFile);
  const mood = moodInput.value.trim();
  if (mood) formData.append("user_text", mood);

  try {
    const resp = await apiFetch("/match/photo", { method: "POST", body: formData });
    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      let detail = "";
      try { detail = JSON.parse(body).detail; } catch {}
      throw new Error(detail || `配诗失败 [${resp.status}]：${body.slice(0, 120)}`);
    }
    const data = await resp.json();
    state.matchResult = data;
    state.currentPoemIdx = 0;
    renderResult(data.analysis, data.warning);
    bgImage.classList.remove("blurred");
    showPhase("phase-result");
  } catch (err) {
    alert(err.message);
    showPhase("phase-upload");
    bgImage.classList.remove("blurred");
  }
});

document.getElementById("to-calendar-btn").addEventListener("click", async () => {
  clearBg();
  await loadCalendar();
  showPhase("phase-calendar");
});

// ── Result ────────────────────────────────────────────────────────────────────
function renderResult(analysis, warning) {
  const tags = [];
  if (analysis.mood)    tags.push(...analysis.mood.split("、").slice(0, 2));
  if (analysis.imagery) tags.push(...analysis.imagery.split(/[、，,]/).slice(0, 3));
  if (analysis.style)   tags.push(analysis.style);
  const tagsHtml = tags.filter(Boolean).map(t => `<span class="tag">${t}</span>`).join("");
  const warnHtml = warning ? `<p class="vision-warning">图片分析受限，已按您的文字配诗</p>` : "";
  analysisTags.innerHTML = warnHtml + tagsHtml;

  state.currentPoemIdx = 0;
  renderCard();
}

function renderCard() {
  const poems = state.matchResult.poems;
  if (!poems || poems.length === 0) {
    cardsViewport.innerHTML = `<div class="poem-card"><p style="color:var(--text-dim);padding:40px 20px;text-align:center">暂未找到匹配的诗词<br>请补充描述文字后重试</p></div>`;
    cardCounter.textContent = "";
    prevBtn.disabled = true;
    nextBtn.disabled = true;
    cardDots.innerHTML = "";
    return;
  }
  const p = poems[state.currentPoemIdx];
  const title = p.title || p.ci_pai || "（无题）";
  const meta  = [p.dynasty, p.author].filter(Boolean).join(" · ");
  const lines = p.content.split("\n").map(l => l.trim()).filter(Boolean);

  cardsViewport.innerHTML = `
    <div class="poem-card glass">
      <p class="poem-meta">${meta}</p>
      <h2 class="poem-title">${title}</h2>
      <div class="poem-divider"></div>
      <div class="poem-body">${lines.map(l => `<p>${l}</p>`).join("")}</div>
    </div>
  `;

  cardCounter.textContent = `${state.currentPoemIdx + 1} / ${poems.length}`;
  prevBtn.disabled = state.currentPoemIdx === 0;
  nextBtn.disabled = state.currentPoemIdx === poems.length - 1;
  cardDots.innerHTML = poems
    .map((_, i) => `<div class="dot ${i === state.currentPoemIdx ? "active" : ""}"></div>`)
    .join("");
}

prevBtn.addEventListener("click", () => {
  if (state.currentPoemIdx > 0) { state.currentPoemIdx--; renderCard(); }
});
nextBtn.addEventListener("click", () => {
  if (state.currentPoemIdx < state.matchResult.poems.length - 1) {
    state.currentPoemIdx++; renderCard();
  }
});

confirmBtn.addEventListener("click", async () => {
  const poem = state.matchResult.poems[state.currentPoemIdx];
  confirmBtn.disabled = true;
  confirmBtn.textContent = "保存中…";

  try {
    if (state.editEntryId) {
      const params = new URLSearchParams({
        poem_id: poem.id,
        photo_path: state.matchResult.photo_path,
        gemini_analysis: JSON.stringify(state.matchResult.analysis),
        user_text: state.matchResult.user_text || "",
      });
      const resp = await apiFetch(`/diary/entries/${state.editEntryId}?${params}`, { method: "PATCH" });
      if (!resp.ok) throw new Error("更新失败");
    } else {
      const resp = await apiFetch("/diary/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          photo_path: state.matchResult.photo_path,
          poem_id: poem.id,
          analysis: state.matchResult.analysis,
          user_text: state.matchResult.user_text || "",
          entry_date: state.uploadDate,
        }),
      });
      if (!resp.ok) throw new Error("保存失败");
    }

    state.editEntryId = null;
    resetUpload();
    clearBg();
    await loadCalendar();
    showPhase("phase-calendar");
  } catch (err) {
    alert(err.message);
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = "选定这首";
  }
});

resetBtn.addEventListener("click", () => {
  state.editEntryId = null;
  resetUpload();
  clearBg();
  showPhase("phase-upload");
});

function resetUpload() {
  state.selectedFile = null;
  state.matchResult = null;
  photoInput.value = "";
  moodInput.value = "";
  matchBtn.disabled = true;
  state.uploadDate = todayISO();
  dateInput.value = state.uploadDate;
  uploadInner.innerHTML = `
    <svg class="upload-icon" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="6" y="14" width="36" height="26" rx="4" stroke="currentColor" stroke-width="1.5"/>
      <circle cx="24" cy="27" r="7" stroke="currentColor" stroke-width="1.5"/>
      <path d="M18 14l3-5h6l3 5" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
      <circle cx="36" cy="21" r="2" fill="currentColor" opacity="0.5"/>
    </svg>
    <p class="upload-hint">拍摄或选择照片</p>
  `;
}

// ── Calendar ──────────────────────────────────────────────────────────────────
async function loadCalendar() {
  const resp = await apiFetch(`/diary/calendar?year=${state.calYear}&month=${state.calMonth}`);
  state.calEntries = await resp.json();
  closePanel();
  renderCalendar();
}

function renderCalendar() {
  calTitle.textContent = CN_MONTHS[state.calMonth - 1];

  const firstDay    = new Date(state.calYear, state.calMonth - 1, 1).getDay();
  const daysInMonth = new Date(state.calYear, state.calMonth, 0).getDate();
  const today       = new Date();

  const dayMap = {};
  state.calEntries.forEach(d => {
    const day = parseInt(d.date.split("-")[2], 10);
    dayMap[day] = d.entries;
  });

  const cells = [];
  for (let i = 0; i < firstDay; i++) {
    cells.push('<div class="cal-day empty"></div>');
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const entries = dayMap[d];
    const isToday = (today.getFullYear() === state.calYear &&
                     today.getMonth() + 1 === state.calMonth &&
                     today.getDate() === d);
    const dateStr = `${state.calYear}-${String(state.calMonth).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const isSelected = state.selectedDay === dateStr;

    let cls = "cal-day";
    if (entries)    cls += " has-entry";
    if (isToday)    cls += " today";
    if (isSelected) cls += " selected";

    let thumbHtml = "";
    if (entries) {
      const photos = entries.filter(e => e.photo_path).slice(0, 3);
      if (photos.length === 1) {
        thumbHtml = `<img class="cal-thumb-single" src="/photo/${photos[0].photo_path}" loading="lazy">`;
      } else if (photos.length > 1) {
        thumbHtml = `<div class="cal-thumbs">${
          photos.map(e => `<img class="cal-thumb" src="/photo/${e.photo_path}" loading="lazy">`).join("")
        }</div>`;
      }
    }

    const attr = entries ? `data-date="${dateStr}"` : "";
    cells.push(`
      <div class="${cls}" ${attr}>
        <span class="cal-num">${d}</span>
        ${thumbHtml}
      </div>
    `);
  }
  calGrid.innerHTML = cells.join("");

  calGrid.querySelectorAll(".cal-day.has-entry").forEach(el => {
    el.addEventListener("click", () => openDayPanel(el.dataset.date));
  });
}

document.getElementById("cal-prev").addEventListener("click", async () => {
  state.calMonth--;
  if (state.calMonth < 1) { state.calMonth = 12; state.calYear--; }
  await loadCalendar();
});
document.getElementById("cal-next").addEventListener("click", async () => {
  state.calMonth++;
  if (state.calMonth > 12) { state.calMonth = 1; state.calYear++; }
  await loadCalendar();
});

document.getElementById("cal-add").addEventListener("click", () => {
  state.editEntryId = null;
  state.uploadDate = todayISO();
  dateInput.value = state.uploadDate;
  showPhase("phase-upload");
});

// ── Day panel ──────────────────────────────────────────────────────────────────
async function openDayPanel(dateStr) {
  state.selectedDay = dateStr;
  renderCalendar();

  const [year, month] = dateStr.split("-");
  const resp = await apiFetch(`/diary/entries?year=${year}&month=${month}`);
  const all = await resp.json();
  state.dayEntries = all.filter(e => e.date === dateStr);

  renderDayPanel(dateStr);
  phaseCalendar.classList.add("has-panel");
}

function closePanel() {
  state.selectedDay = null;
  phaseCalendar.classList.remove("has-panel");
  calPanelInner.innerHTML = "";
  clearBg();
}

function renderDayPanel(dateStr) {
  const entries = state.dayEntries;
  const displayDate = dateStr.replace(/-/g, " · ");

  let html = `
    <div class="panel-date">
      <span>${displayDate}</span>
      <button class="panel-add-btn" data-date="${dateStr}">＋ 添加</button>
    </div>
  `;

  for (const entry of entries) {
    const poem  = entry.poem;
    const title = poem ? (poem.title || poem.ci_pai || "（无题）") : "";
    const meta  = poem ? [poem.dynasty, poem.author].filter(Boolean).join(" · ") : "";
    const lines = poem ? poem.content.split("\n").map(l => l.trim()).filter(Boolean) : [];

    html += `
      <div class="panel-entry" data-entry-id="${entry.id}">
        ${entry.photo_path
          ? `<img class="panel-photo" src="/photo/${entry.photo_path}" alt="">`
          : ""}
        ${poem ? `
          <div class="panel-poem">
            ${meta ? `<p class="poem-meta">${meta}</p>` : ""}
            <h3 class="poem-title">${title}</h3>
            <div class="poem-divider"></div>
            <div class="poem-body">${lines.map(l => `<p>${l}</p>`).join("")}</div>
          </div>
        ` : ""}
        <div class="panel-actions">
          <button class="btn-ghost-sm rematch-btn" data-entry-id="${entry.id}">重新配诗</button>
          <button class="btn-ghost-sm danger delete-btn" data-entry-id="${entry.id}">删除</button>
        </div>
      </div>
    `;
  }

  calPanelInner.innerHTML = html;

  const firstPhoto = entries.find(e => e.photo_path);
  if (firstPhoto) setPhotoBg(firstPhoto.photo_path, false);
  else clearBg();

  calPanelInner.querySelector(".panel-add-btn")?.addEventListener("click", (e) => {
    state.editEntryId = null;
    state.uploadDate = e.currentTarget.dataset.date;
    dateInput.value = state.uploadDate;
    showPhase("phase-upload");
  });

  calPanelInner.querySelectorAll(".rematch-btn").forEach(btn => {
    btn.addEventListener("click", () => rematchEntry(parseInt(btn.dataset.entryId)));
  });

  calPanelInner.querySelectorAll(".delete-btn").forEach(btn => {
    btn.addEventListener("click", () => deleteEntry(parseInt(btn.dataset.entryId), dateStr));
  });

  calPanelInner.querySelectorAll(".panel-photo").forEach(img => {
    img.addEventListener("click", () => setPhotoBg(img.src.replace("/photo/", ""), false));
  });
}

async function deleteEntry(entryId, dateStr) {
  if (!confirm(`删除 ${dateStr} 的这条记录？`)) return;

  const resp = await apiFetch(`/diary/entries/${entryId}?delete_photo=true`, { method: "DELETE" });
  if (!resp.ok && resp.status !== 204) { alert("删除失败"); return; }

  await loadCalendar();
  const dayData = state.calEntries.find(d => d.date === dateStr);
  if (dayData && dayData.entries.length > 0) {
    await openDayPanel(dateStr);
  } else {
    closePanel();
  }
}

async function rematchEntry(entryId) {
  const entry = state.dayEntries.find(e => e.id === entryId);
  showPhase("phase-loading");

  try {
    const formData = new FormData();
    formData.append("user_text", entry.user_text || "");
    const resp = await apiFetch(`/diary/entries/${entryId}/rematch`, {
      method: "POST", body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || "重新配诗失败");
    }
    const data = await resp.json();
    state.matchResult = {
      photo_path: data.photo_path,
      analysis: data.analysis,
      user_text: data.user_text,
      poems: data.poems,
    };
    state.editEntryId = entryId;
    state.currentPoemIdx = 0;
    renderResult(data.analysis);
    if (data.photo_path) setPhotoBg(data.photo_path, false);
    showPhase("phase-result");
  } catch (err) {
    alert(err.message);
    showPhase("phase-calendar");
  }
}

// ── Monthly poems ─────────────────────────────────────────────────────────────
document.getElementById("cal-poems-btn").addEventListener("click", async () => {
  poemsTitle.textContent = CN_MONTHS[state.calMonth - 1];

  const resp = await apiFetch(`/diary/entries?year=${state.calYear}&month=${state.calMonth}`);
  const entries = (await resp.json()).sort((a, b) => a.date.localeCompare(b.date));

  if (!entries.length) {
    poemsList.innerHTML = `<p style="color:var(--text-dim);letter-spacing:0.12em;padding:20px 0">本月暂无记录</p>`;
  } else {
    poemsList.innerHTML = entries.map(entry => {
      const poem  = entry.poem;
      const title = poem ? (poem.title || poem.ci_pai || "（无题）") : "（无诗）";
      const meta  = poem ? [poem.dynasty, poem.author].filter(Boolean).join(" · ") : "";
      const lines = poem ? poem.content.split("\n").map(l => l.trim()).filter(Boolean) : [];
      const snippet = lines.slice(0, 2).join(" / ");
      const dateLabel = entry.date.replace(/-/g, " · ");

      return `
        <div class="poems-entry">
          ${entry.photo_path
            ? `<img class="poems-thumb" src="/photo/${entry.photo_path}" loading="lazy">`
            : `<div class="poems-thumb-placeholder"></div>`}
          <div class="poems-info">
            <div class="poems-date-label">${dateLabel}</div>
            <div class="poems-poem-title">${title}</div>
            ${meta ? `<div class="poems-poem-meta">${meta}</div>` : ""}
            ${snippet ? `<div class="poems-poem-snippet">${snippet}</div>` : ""}
          </div>
        </div>
      `;
    }).join("");
  }

  clearBg();
  showPhase("phase-poems");
});

document.getElementById("poems-back").addEventListener("click", () => {
  showPhase("phase-calendar");
});

// ── Onboarding ────────────────────────────────────────────────────────────────
const ONBOARDING_STEPS = [
  {
    selector: "#upload-zone",
    tip: "点这里拍摄，或从相册选择一张照片",
  },
  {
    selector: "#mood-input",
    tip: "输入此刻的心情或场景描述，帮助配出更贴切的诗句（可选）",
  },
  {
    selector: "#match-btn",
    tip: "点击「配诗」，AI 将在38万首古诗词中为你寻觅最合适的几句",
  },
];

let onboardingStep = 0;
const onboardingOverlay  = document.getElementById("onboarding-overlay");
const onboardingSpotlight = document.getElementById("onboarding-spotlight");
const onboardingTooltip  = document.getElementById("onboarding-tooltip");
const onboardingTip      = document.getElementById("onboarding-tip");
const onboardingNext     = document.getElementById("onboarding-next");
const onboardingSkip     = document.getElementById("onboarding-skip");

function startOnboarding() {
  onboardingStep = 0;
  onboardingOverlay.classList.add("active");
  showOnboardingStep();
}

function showOnboardingStep() {
  const step = ONBOARDING_STEPS[onboardingStep];
  const target = document.querySelector(step.selector);
  if (!target) { finishOnboarding(); return; }

  const rect = target.getBoundingClientRect();
  const pad = 10;

  onboardingSpotlight.style.left   = `${rect.left - pad}px`;
  onboardingSpotlight.style.top    = `${rect.top - pad}px`;
  onboardingSpotlight.style.width  = `${rect.width + pad * 2}px`;
  onboardingSpotlight.style.height = `${rect.height + pad * 2}px`;

  onboardingTip.textContent = step.tip;
  onboardingNext.textContent =
    onboardingStep === ONBOARDING_STEPS.length - 1 ? "开始使用" : "下一步 →";

  // Position tooltip below spotlight, clamped to viewport
  const tooltipTop = rect.bottom + pad + 16;
  const maxTop = window.innerHeight - 180;
  onboardingTooltip.style.top = `${Math.min(tooltipTop, maxTop)}px`;
}

function finishOnboarding() {
  onboardingOverlay.classList.remove("active");
  localStorage.setItem("shiju_onboarded", "1");
}

onboardingNext.addEventListener("click", () => {
  onboardingStep++;
  if (onboardingStep >= ONBOARDING_STEPS.length) {
    finishOnboarding();
  } else {
    showOnboardingStep();
  }
});

onboardingSkip.addEventListener("click", finishOnboarding);

// ── Init ──────────────────────────────────────────────────────────────────────
if (authToken) {
  document.getElementById("landing-username").textContent = authUsername || "";
  showPhase("phase-landing");
} else {
  showPhase("phase-auth");
}
