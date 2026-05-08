const API = "http://127.0.0.1:8000";

// ─── Utilities ────────────────────────────────────────────────────────────────

function showToast(msg, isError = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `fixed bottom-20 left-1/2 -translate-x-1/2 px-4 py-2 rounded-full text-sm text-white z-50 ${
    isError ? "bg-red-500" : "bg-stone-700"
  }`;
  t.style.opacity = "1";
  setTimeout(() => { t.style.opacity = "0"; }, 2500);
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// ─── Tab navigation ────────────────────────────────────────────────────────────

function initTabs() {
  const tabs = document.querySelectorAll("[data-tab]");
  const sections = document.querySelectorAll(".tab-section");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("text-stone-800", "border-t-2", "border-stone-600"));
      tab.classList.add("text-stone-800", "border-t-2", "border-stone-600");
      sections.forEach(s => s.classList.remove("active"));
      document.getElementById("section-" + tab.dataset.tab).classList.add("active");
      if (tab.dataset.tab === "library") loadLibrary();
      if (tab.dataset.tab === "stats") loadStats();
      if (tab.dataset.tab === "diary") initCalendar();
    });
  });
  // Activate first tab
  tabs[0]?.click();
}

// ─── 诗词库 Tab ────────────────────────────────────────────────────────────────

let libraryPoems = [];

async function loadLibrary() {
  try {
    libraryPoems = await api("GET", "/poems");
    renderLibrary(libraryPoems);
    populateFilters(libraryPoems);
  } catch (e) {
    showToast(e.message, true);
  }
}

function renderLibrary(poems) {
  const list = document.getElementById("poem-list");
  if (!poems.length) {
    list.innerHTML = `<p class="text-center text-stone-400 py-12">还没有收录诗词，试试上方搜索框</p>`;
    return;
  }
  list.innerHTML = poems.map(p => poemCard(p)).join("");
  list.querySelectorAll(".memorized-btn").forEach(btn => {
    btn.addEventListener("click", () => toggleMemorized(parseInt(btn.dataset.id), btn.dataset.memorized === "true"));
  });
  list.querySelectorAll(".delete-btn").forEach(btn => {
    btn.addEventListener("click", () => deletePoem(parseInt(btn.dataset.id)));
  });
}

function poemCard(p) {
  const memLabel = p.is_memorized ? "✓ 已背会" : "背会了";
  const memColor = p.is_memorized ? "bg-green-100 text-green-700" : "bg-stone-100 text-stone-500";
  const preview = p.content.split("\n").slice(0, 2).join(" / ");
  return `
  <div class="bg-white rounded-xl p-4 shadow-sm border border-stone-100">
    <div class="flex justify-between items-start mb-1">
      <div>
        <span class="font-semibold text-stone-800">${p.title || p.ci_pai || "（无题）"}</span>
        <span class="text-xs text-stone-400 ml-2">${[p.dynasty, p.author].filter(Boolean).join(" · ")}</span>
        ${p.ci_pai ? `<span class="text-xs text-amber-600 ml-1">【${p.ci_pai}】</span>` : ""}
      </div>
      <button class="delete-btn text-stone-300 hover:text-red-400 text-xs ml-2" data-id="${p.id}">✕</button>
    </div>
    <p class="text-stone-500 text-sm poem-content truncate mb-3">${preview}</p>
    <button class="memorized-btn text-xs px-3 py-1 rounded-full ${memColor}" data-id="${p.id}" data-memorized="${p.is_memorized}">${memLabel}</button>
  </div>`;
}

function populateFilters(poems) {
  const dynasties = [...new Set(poems.map(p => p.dynasty).filter(Boolean))];
  const ciPais = [...new Set(poems.map(p => p.ci_pai).filter(Boolean))];
  const dSel = document.getElementById("filter-dynasty");
  const cSel = document.getElementById("filter-cipai");
  dSel.innerHTML = `<option value="">朝代</option>` + dynasties.map(d => `<option>${d}</option>`).join("");
  cSel.innerHTML = `<option value="">词牌</option>` + ciPais.map(c => `<option>${c}</option>`).join("");
}

function applyFilters() {
  const dynasty = document.getElementById("filter-dynasty").value;
  const ciPai = document.getElementById("filter-cipai").value;
  const memorized = document.getElementById("filter-memorized").checked;
  let filtered = libraryPoems;
  if (dynasty) filtered = filtered.filter(p => p.dynasty === dynasty);
  if (ciPai) filtered = filtered.filter(p => p.ci_pai === ciPai);
  if (memorized) filtered = filtered.filter(p => p.is_memorized);
  renderLibrary(filtered);
}

async function toggleMemorized(id, current) {
  try {
    await api("PATCH", `/poems/${id}/memorized`, { is_memorized: !current });
    showToast(current ? "已取消背会标记" : "已标记为背会 ✓");
    loadLibrary();
  } catch (e) { showToast(e.message, true); }
}

async function deletePoem(id) {
  if (!confirm("确认删除这首诗词？")) return;
  try {
    await api("DELETE", `/poems/${id}`);
    showToast("已删除");
    loadLibrary();
  } catch (e) { showToast(e.message, true); }
}

// Smart input
let smartInputTimer;
function initSmartInput() {
  const input = document.getElementById("smart-input");
  const results = document.getElementById("smart-results");

  input.addEventListener("input", debounce(async () => {
    const q = input.value.trim();
    if (!q) { results.innerHTML = ""; return; }
    results.innerHTML = `<p class="text-stone-400 text-sm text-center py-4">搜索中…</p>`;
    try {
      const data = await api("POST", "/search/smart-input", { query: q });
      if (!data.candidates.length) {
        results.innerHTML = `<p class="text-stone-400 text-sm text-center py-4">未找到匹配诗词</p>`;
        return;
      }
      results.innerHTML = data.candidates.map(p => `
        <div class="bg-amber-50 rounded-lg p-3 border border-amber-100">
          <div class="flex justify-between items-start">
            <div class="flex-1 min-w-0 mr-2">
              <span class="font-medium text-stone-800">${p.title || p.ci_pai || "（无题）"}</span>
              <span class="text-xs text-stone-400 ml-2">${[p.dynasty, p.author].filter(Boolean).join(" · ")}</span>
            </div>
            <button class="confirm-btn flex-shrink-0 text-xs bg-amber-500 hover:bg-amber-600 text-white px-3 py-1 rounded-full" data-id="${p.id}">收录</button>
          </div>
          <p class="text-stone-500 text-sm mt-1 poem-content">${p.content.split("\n").slice(0,3).join(" / ")}</p>
        </div>
      `).join("");
      results.querySelectorAll(".confirm-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
          try {
            await api("POST", "/search/confirm", { poem_id: parseInt(btn.dataset.id) });
            showToast("已收录 ✓");
            input.value = "";
            results.innerHTML = "";
            loadLibrary();
          } catch (e) { showToast(e.message, true); }
        });
      });
    } catch (e) {
      results.innerHTML = `<p class="text-red-400 text-sm text-center py-4">${e.message}</p>`;
    }
  }, 400));
}

// ─── 统计 Tab ──────────────────────────────────────────────────────────────────

async function loadStats() {
  try {
    const s = await api("GET", "/poems/stats");
    document.getElementById("stats-total").textContent = s.total;
    document.getElementById("stats-memorized").textContent = s.memorized;
    const pct = s.total ? Math.round(s.memorized / s.total * 100) : 0;
    document.getElementById("stats-pct").textContent = pct + "%";
    document.getElementById("stats-pct-bar").style.width = pct + "%";

    const dynastyEl = document.getElementById("stats-dynasty");
    const total = Object.values(s.by_dynasty).reduce((a, b) => a + b, 0) || 1;
    dynastyEl.innerHTML = Object.entries(s.by_dynasty)
      .sort((a, b) => b[1] - a[1])
      .map(([d, n]) => `
        <div>
          <div class="flex justify-between text-sm mb-1"><span>${d}</span><span class="text-stone-400">${n}</span></div>
          <div class="h-2 bg-stone-100 rounded-full"><div class="h-2 bg-amber-400 rounded-full" style="width:${Math.round(n/total*100)}%"></div></div>
        </div>`).join("");
  } catch (e) { showToast(e.message, true); }
}

// ─── 日记 Tab ──────────────────────────────────────────────────────────────────

let calYear = new Date().getFullYear();
let calMonth = new Date().getMonth() + 1;
let calEntryDates = {};

async function initCalendar() {
  await renderCalendar();
  initPhotoUpload();
}

async function renderCalendar() {
  const data = await api("GET", `/diary/calendar?year=${calYear}&month=${calMonth}`).catch(() => []);
  calEntryDates = {};
  data.forEach(e => { calEntryDates[e.date] = e; });

  document.getElementById("cal-label").textContent =
    `${calYear}年${calMonth}月`;

  const grid = document.getElementById("cal-grid");
  const firstDay = new Date(calYear, calMonth - 1, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth, 0).getDate();

  let html = "";
  for (let i = 0; i < firstDay; i++) html += `<div></div>`;
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${calYear}-${String(calMonth).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const hasEntry = calEntryDates[dateStr];
    const isToday = dateStr === new Date().toISOString().slice(0, 10);
    html += `
      <div class="cal-day flex flex-col items-center cursor-pointer py-1 rounded-lg hover:bg-amber-50 ${isToday ? "font-bold" : ""}"
           data-date="${dateStr}">
        <span class="text-sm ${isToday ? "text-amber-600" : "text-stone-600"}">${d}</span>
        ${hasEntry ? `<span class="w-1.5 h-1.5 rounded-full bg-amber-400 mt-0.5"></span>` : `<span class="w-1.5 h-1.5 mt-0.5"></span>`}
      </div>`;
  }
  grid.innerHTML = html;
  grid.querySelectorAll(".cal-day[data-date]").forEach(el => {
    el.addEventListener("click", () => openDayEntries(el.dataset.date));
  });
}

async function openDayEntries(dateStr) {
  if (!calEntryDates[dateStr]) return;
  try {
    const [y, m] = dateStr.split("-").map(Number);
    const entries = await api("GET", `/diary/entries?year=${y}&month=${m}`);
    const dayEntries = entries.filter(e => e.date === dateStr);
    if (!dayEntries.length) return;
    const e = dayEntries[0];
    const modal = document.getElementById("entry-modal");
    document.getElementById("modal-date").textContent = dateStr;
    document.getElementById("modal-scene").textContent = e.scene_description || "";
    document.getElementById("modal-note").textContent = e.note || "";
    if (e.poem) {
      document.getElementById("modal-poem-title").textContent =
        `${e.poem.title || e.poem.ci_pai || "（无题）"} · ${[e.poem.dynasty, e.poem.author].filter(Boolean).join(" ")}`;
      document.getElementById("modal-poem-content").textContent = e.poem.content;
    } else {
      document.getElementById("modal-poem-title").textContent = "";
      document.getElementById("modal-poem-content").textContent = "";
    }
    modal.classList.remove("hidden");
  } catch (err) { showToast(err.message, true); }
}

function initPhotoUpload() {
  const input = document.getElementById("photo-input");
  const preview = document.getElementById("photo-preview");
  const uploadArea = document.getElementById("upload-area");
  const hint = document.getElementById("upload-hint");
  const resultArea = document.getElementById("upload-result");
  const moodInput = document.getElementById("mood-input");
  const searchBtn = document.getElementById("mood-search-btn");

  let currentPhotoPath = null;

  // Photo selection
  uploadArea.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file) return;
    preview.src = URL.createObjectURL(file);
    preview.classList.remove("hidden");
    hint.textContent = "已选择，可重新点击更换";

    const fd = new FormData();
    fd.append("photo", file);
    try {
      const data = await api("POST", "/diary/upload-photo", fd);
      currentPhotoPath = data.photo_path;
    } catch (e) {
      showToast("图片上传失败: " + e.message, true);
    }
  });

  // Poem search by mood text
  async function searchPoems() {
    const mood = moodInput.value.trim();
    if (!mood) { showToast("请先输入意境词", true); return; }

    resultArea.innerHTML = `<p class="text-stone-400 text-sm text-center py-3">匹配中…</p>`;
    try {
      const data = await api("POST", "/search/smart-input", { query: mood });
      if (!data.candidates.length) {
        resultArea.innerHTML = `<p class="text-stone-400 text-sm text-center py-3">未找到匹配诗词，换几个词试试</p>`;
        return;
      }
      const today = new Date().toISOString().slice(0, 10);
      resultArea.innerHTML = data.candidates.map(p => `
        <div class="bg-white rounded-xl p-3 mb-2 border border-stone-100 shadow-sm">
          <div class="flex justify-between items-start gap-2">
            <div class="min-w-0">
              <span class="font-medium text-stone-800">${p.title || p.ci_pai || "（无题）"}</span>
              <span class="text-xs text-stone-400 ml-2">${[p.dynasty, p.author].filter(Boolean).join(" · ")}</span>
              ${p.ci_pai && p.title ? `<span class="text-xs text-amber-600 ml-1">【${p.ci_pai}】</span>` : ""}
            </div>
            <button class="save-diary-btn flex-shrink-0 text-xs bg-stone-700 hover:bg-stone-800 text-white px-3 py-1 rounded-full"
              data-poem-id="${p.id}"
              data-mood="${encodeURIComponent(mood)}">配入日记</button>
          </div>
          <p class="text-stone-500 text-sm mt-2 poem-content">${p.content.split("\n").slice(0,3).join("\n")}</p>
        </div>`).join("");

      resultArea.querySelectorAll(".save-diary-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
          try {
            await api("POST", "/diary/entries", {
              date: today,
              photo_path: currentPhotoPath,
              scene_description: decodeURIComponent(btn.dataset.mood),
              poem_id: parseInt(btn.dataset.poemId),
            });
            showToast("已存入日记 ✓");
            resultArea.innerHTML = "";
            preview.classList.add("hidden");
            hint.textContent = "点击上传今日照片";
            input.value = "";
            moodInput.value = "";
            currentPhotoPath = null;
            await renderCalendar();
          } catch (e) { showToast(e.message, true); }
        });
      });
    } catch (e) {
      resultArea.innerHTML = `<p class="text-red-400 text-sm text-center py-3">${e.message}</p>`;
    }
  }

  searchBtn.addEventListener("click", searchPoems);
  moodInput.addEventListener("keydown", e => { if (e.key === "Enter") searchPoems(); });
}

// ─── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initSmartInput();
  document.getElementById("filter-dynasty").addEventListener("change", applyFilters);
  document.getElementById("filter-cipai").addEventListener("change", applyFilters);
  document.getElementById("filter-memorized").addEventListener("change", applyFilters);
  document.getElementById("cal-prev").addEventListener("click", async () => {
    calMonth--; if (calMonth < 1) { calMonth = 12; calYear--; }
    await renderCalendar();
  });
  document.getElementById("cal-next").addEventListener("click", async () => {
    calMonth++; if (calMonth > 12) { calMonth = 1; calYear++; }
    await renderCalendar();
  });
  document.getElementById("modal-close").addEventListener("click", () => {
    document.getElementById("entry-modal").classList.add("hidden");
  });
});
