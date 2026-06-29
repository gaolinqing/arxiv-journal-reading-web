const DATA_URL = "data/latest.json";
const STATE_KEY = "arxiv_prl_reading_state_v1";
const DEFAULT_PRD_SOURCE_URL = "https://journals.aps.org/prd/recent";

const paperList = document.querySelector("#paperList");
const template = document.querySelector("#paperTemplate");
const sourceTabs = Array.from(document.querySelectorAll("[data-filter]"));
const dateTabs = document.querySelector("#dateTabs");
const searchInput = document.querySelector("#searchInput");
const statusBox = document.querySelector("#status");
const paperCount = document.querySelector("#paperCount");
const likedCount = document.querySelector("#likedCount");
const exportButton = document.querySelector("#exportButton");
const refreshButton = document.querySelector("#refreshButton");
const likedTableSection = document.querySelector("#likedTableSection");
const likedTableBody = document.querySelector("#likedTableBody");

let papers = [];
let currentFilter = "all";
let currentDate = "";
let state = loadState();
let datasetWarnings = [];
let generatedDate = new Date().toISOString().slice(0, 10);
let prlSourceUrl = "";
let prdSourceUrl = DEFAULT_PRD_SOURCE_URL;

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(STATE_KEY)) || {};
  } catch {
    return {};
  }
}

function saveState() {
  localStorage.setItem(STATE_KEY, JSON.stringify(state));
}

function paperKey(paper) {
  return paper.id || paper.doi || paper.url || paper.title;
}

function getPaperState(paper) {
  return state[paperKey(paper)] || {};
}

function updatePaperState(paper, patch) {
  const key = paperKey(paper);
  state[key] = { ...state[key], ...patch, updatedAt: new Date().toISOString() };
  saveState();
  render();
}

function setStatus(message) {
  statusBox.hidden = !message;
  statusBox.textContent = message || "";
}

function setStatusHtml(htmlText) {
  statusBox.hidden = !htmlText;
  statusBox.innerHTML = htmlText || "";
}

async function loadPapers() {
  setStatus("Loading papers...");
  try {
    const response = await fetch(`${DATA_URL}?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    papers = data.papers || [];
    datasetWarnings = data.warnings || [];
    prlSourceUrl = data.sources?.prl_recent_url || "";
    prdSourceUrl = data.sources?.prd_recent_url || DEFAULT_PRD_SOURCE_URL;
    generatedDate = (data.local_date || data.generated_at || new Date().toISOString()).slice(0, 10);
    currentDate = generatedDate;
    renderDateTabs();
    setStatus("");
    render();
  } catch (error) {
    papers = [];
    datasetWarnings = [];
    setStatus(`Could not load data/latest.json. Run scripts/fetch_papers.py or open through a local web server. ${error.message}`);
    render();
  }
}

function normalizeText(value) {
  return String(value || "").toLowerCase();
}

function matchesFilter(paper) {
  const paperState = getPaperState(paper);
  if (paperState.hidden && currentFilter !== "liked") return false;
  if (currentFilter === "liked") return paperState.preference === "liked";
  if (currentFilter === "all") return true;
  if (currentFilter === "prl") return paper.source === "prl";
  return paper.category === currentFilter;
}

function parseDateOnly(value) {
  const match = String(value || "").match(/\d{4}-\d{2}-\d{2}/);
  if (match) return match[0];
  return "";
}

function formatDateLabel(dateText, index) {
  const date = new Date(`${dateText}T00:00:00Z`);
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const weekday = date.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
  return `${month}${day} ${weekday}`;
}

function dateOffset(baseDate, offsetDays) {
  const date = new Date(`${baseDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - offsetDays);
  return date.toISOString().slice(0, 10);
}

function dateCount(dateText) {
  if (currentFilter === "liked") return likedPapers().length;
  return papers.filter((paper) => matchesFilter(paper) && parseDateOnly(paper.published || paper.updated) === dateText).length;
}

function dateOptions() {
  const options = [];
  for (let index = 0; index < 7; index += 1) {
    const dateText = dateOffset(generatedDate, index);
    options.push({ dateText, index, count: dateCount(dateText) });
  }
  return options;
}

function ensureSelectableDate() {
  if (currentFilter === "prl" || currentFilter === "liked") return;
  if (dateCount(currentDate) > 0) return;
  const firstAvailable = dateOptions().find((option) => option.count > 0);
  if (firstAvailable) currentDate = firstAvailable.dateText;
}

function renderDateTabs() {
  ensureSelectableDate();
  dateTabs.innerHTML = "";
  for (const { dateText, index, count } of dateOptions()) {
    const button = document.createElement("button");
    button.className = "tab date-tab";
    button.type = "button";
    button.dataset.date = dateText;
    button.textContent = formatDateLabel(dateText, index);
    button.disabled = currentFilter !== "prl" && currentFilter !== "liked" && count === 0;
    button.classList.toggle("is-active", dateText === currentDate);
    button.addEventListener("click", () => {
      if (button.disabled) return;
      currentDate = dateText;
      renderDateTabs();
      render();
    });
    dateTabs.appendChild(button);
  }
}

function matchesDate(paper) {
  if (currentFilter === "liked") return true;
  const paperDate = parseDateOnly(paper.published || paper.updated);
  return paperDate === currentDate;
}

function matchesSearch(paper) {
  const query = normalizeText(searchInput.value).trim();
  if (!query) return true;
  const haystack = normalizeText([
    paper.title,
    paper.abstract,
    (paper.authors || []).join(" "),
    paper.id,
    paper.doi,
    paper.source_label,
  ].join(" "));
  return haystack.includes(query);
}

function visiblePapers() {
  return papers.filter((paper) => matchesFilter(paper) && matchesDate(paper) && matchesSearch(paper));
}

function likedPapers() {
  return papers.filter((paper) => getPaperState(paper).preference === "liked");
}

function render() {
  const shown = visiblePapers();
  const liked = likedPapers();

  paperList.innerHTML = "";
  paperCount.textContent = shown.length;
  likedCount.textContent = liked.length;

  if (currentFilter === "prl" && prlSourceUrl) {
    setStatusHtml(`
      <div class="journal-links">
        <a href="${escapeAttribute(prlSourceUrl)}" target="_blank" rel="noopener">Open PRL</a>
        <a href="${escapeAttribute(prdSourceUrl)}" target="_blank" rel="noopener">Open PRD</a>
      </div>
    `);
  } else if (!shown.length && papers.length) {
    setStatus("No papers match the current source and date.");
  } else if (shown.length) {
    setStatus("");
  }

  for (const paper of shown) {
    paperList.appendChild(renderPaper(paper));
  }

  renderLikedTable(liked);
}

function renderPaper(paper) {
  const node = template.content.firstElementChild.cloneNode(true);
  const paperState = getPaperState(paper);
  const sourceLabel = paper.source_label || paper.category || paper.source || "paper";

  node.querySelector(".source-pill").textContent = sourceLabel;
  node.querySelector(".date-text").textContent = paper.published || "";
  node.querySelector(".paper-title").textContent = paper.title || "Untitled";
  node.querySelector(".authors").textContent = (paper.authors || []).join(", ");
  node.querySelector(".abstract").textContent = paper.abstract || "No abstract available.";

  const likeButton = node.querySelector(".like-button");
  const dislikeButton = node.querySelector(".dislike-button");
  const hideButton = node.querySelector(".hide-button");
  const readLink = node.querySelector(".read-link");
  const pdfLink = node.querySelector(".pdf-link");

  likeButton.classList.toggle("is-selected", paperState.preference === "liked");
  dislikeButton.classList.toggle("is-selected", paperState.preference === "disliked");

  likeButton.addEventListener("click", () => {
    const next = paperState.preference === "liked" ? null : "liked";
    updatePaperState(paper, { preference: next });
  });

  dislikeButton.addEventListener("click", () => {
    const next = paperState.preference === "disliked" ? null : "disliked";
    updatePaperState(paper, { preference: next });
  });

  hideButton.addEventListener("click", () => updatePaperState(paper, { hidden: true }));

  readLink.href = paper.url || paper.doi_url || "#";
  pdfLink.href = paper.pdf_url || paper.url || paper.doi_url || "#";
  pdfLink.hidden = !paper.pdf_url;

  return node;
}

function renderLikedTable(liked) {
  likedTableSection.hidden = currentFilter !== "liked" || liked.length === 0;
  likedTableBody.innerHTML = "";

  for (const paper of liked) {
    const row = document.createElement("tr");
    const id = paper.id || paper.doi || "";
    const link = paper.url || paper.doi_url || paper.pdf_url || "";
    row.innerHTML = `
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td>${link ? `<a href="${escapeAttribute(link)}" target="_blank" rel="noopener">Open</a>` : ""}</td>
    `;
    row.children[0].textContent = paper.title || "";
    row.children[1].textContent = id;
    row.children[2].textContent = (paper.authors || []).join(", ");
    row.children[3].textContent = paper.source_label || paper.source || "";
    likedTableBody.appendChild(row);
  }
}

function escapeAttribute(value) {
  return String(value || "").replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function exportLikedCsv() {
  const liked = likedPapers();
  const header = ["title", "id_or_doi", "authors", "source", "published", "url", "pdf_url"];
  const rows = liked.map((paper) => [
    paper.title,
    paper.id || paper.doi || "",
    (paper.authors || []).join("; "),
    paper.source_label || paper.source || "",
    paper.published || "",
    paper.url || paper.doi_url || "",
    paper.pdf_url || "",
  ]);

  const csv = [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `liked_papers_${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

sourceTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    currentFilter = tab.dataset.filter;
    sourceTabs.forEach((item) => item.classList.toggle("is-active", item === tab));
    renderDateTabs();
    render();
  });
});

searchInput.addEventListener("input", render);
exportButton.addEventListener("click", exportLikedCsv);
refreshButton.addEventListener("click", loadPapers);

loadPapers();
