const $ = (id) => document.getElementById(id);
const today = new Date().toISOString().slice(0, 10);
const weekAgo = new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10);
const labels = {note: "笔记", meeting: "会议", result: "成果", blocker: "阻塞"};
$("report-start").value = weekAgo;
$("report-end").value = today;
$("evidence-form").elements.occurred_on.value = today;

function notice(message) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}
async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}
function params(values) {
  return new URLSearchParams(Object.entries(values).filter(([, value]) => value)).toString();
}
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}
function empty(container, message) {
  container.replaceChildren(node("div", "empty", message));
}
async function loadEvidence() {
  const items = await api("/api/evidence?" + params({project: $("project").value.trim(),
    search: $("search").value.trim(), kind: $("kind-filter").value,
    start: $("start-filter").value, end: $("end-filter").value}));
  const list = $("evidence-list");
  list.replaceChildren();
  $("result-count").textContent = `找到 ${items.length} 条记录`;
  if (!items.length) return empty(list, "暂无记录，新增一条项目笔记开始积累。");
  for (const item of items) {
    const card = node("article", "item");
    const head = node("div", "item-head");
    const title = node("h3", "", item.title);
    title.prepend(node("span", "badge " + item.kind, labels[item.kind] || item.kind));
    head.append(title, node("span", "meta", item.occurred_on));
    card.append(head, node("p", "", item.content));
    if (item.source_url && /^https?:\/\//i.test(item.source_url)) {
      const link = node("a", "", "查看来源 ↗");
      link.href = item.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      card.append(link);
    }
    card.append(node("span", "meta", `  #${item.id} · ${item.project}`));
    list.append(card);
  }
}
async function loadTasks() {
  const items = await api("/api/tasks?" + params({project: $("project").value.trim()}));
  const list = $("task-list");
  list.replaceChildren();
  if (!items.length) return empty(list, "暂无任务。");
  for (const item of items) {
    const row = node("article", "item task-line");
    row.append(node("h3", "", item.title), node("span", "meta", item.due_on || "无截止日期"));
    const status = node("select");
    status.setAttribute("aria-label", `${item.title} 状态`);
    for (const [value, label] of [["todo", "待办"], ["doing", "进行中"], ["done", "完成"]]) {
      const option = node("option", "", label);
      option.value = value;
      option.selected = item.status === value;
      status.append(option);
    }
    const evidence = node("input");
    evidence.type = "number";
    evidence.min = "1";
    evidence.placeholder = "关联证据 ID";
    evidence.setAttribute("aria-label", `${item.title} 关联证据 ID`);
    evidence.value = item.evidence_id || "";
    const save = node("button", "", "更新");
    save.onclick = async () => {
      try {
        await api(`/api/tasks/${item.id}`, {method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({status: status.value, evidence_id: evidence.value ? Number(evidence.value) : null})});
        notice("任务已更新");
        await loadTasks();
      } catch (error) { notice(error.message); }
    };
    row.append(status, evidence, save);
    list.append(row);
  }
}
async function loadCurrent() {
  try {
    notice("");
    if (!$("evidence-view").hidden) await loadEvidence();
    if (!$("tasks-view").hidden) await loadTasks();
  } catch (error) { notice(error.message); }
}
document.querySelectorAll(".nav button").forEach((button) => button.onclick = () => {
  document.querySelectorAll(".nav button").forEach((item) => item.classList.toggle("active", item === button));
  document.querySelectorAll(".view").forEach((view) => view.hidden = view.id !== button.dataset.view + "-view");
  loadCurrent();
});
$("project").onchange = loadCurrent;
$("search-button").onclick = loadEvidence;
$("search").onkeydown = (event) => { if (event.key === "Enter") loadEvidence(); };
for (const id of ["kind-filter", "start-filter", "end-filter"]) $(id).onchange = loadEvidence;
$("new-evidence").onclick = () => $("evidence-dialog").showModal();
$("new-task").onclick = () => $("task-dialog").showModal();
document.querySelectorAll("[data-close]").forEach((button) => button.onclick = () => button.closest("dialog").close());
for (const [formId, path, dialogId] of [["evidence-form", "/api/evidence", "evidence-dialog"], ["task-form", "/api/tasks", "task-dialog"]]) {
  $(formId).onsubmit = async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.target));
    data.project = $("project").value.trim();
    try {
      await api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
      $(dialogId).close();
      event.target.reset();
      $("evidence-form").elements.occurred_on.value = today;
      await loadCurrent();
    } catch (error) { notice(error.message); }
  };
}
$("generate").onclick = async () => {
  try {
    const data = await api("/api/report?" + params({project: $("project").value.trim(),
      start: $("report-start").value, end: $("report-end").value}));
    $("report-output").textContent = data.markdown;
    notice("");
  } catch (error) { notice(error.message); }
};
$("copy-report").onclick = async () => {
  await navigator.clipboard.writeText($("report-output").textContent);
  notice("已复制 Markdown");
};
api("/api/health").then(() => {
  $("connection").textContent = "seekdb 已连接";
  $("connection").className = "connection ok";
  loadCurrent();
}).catch((error) => {
  $("connection").textContent = "seekdb 未连接";
  $("connection").className = "connection error";
  notice(error.message);
});
