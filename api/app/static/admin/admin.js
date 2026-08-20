async function apiFetch(path, options = {}) {
  const opts = { ...options };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const res = await fetch(path, opts);
  if (res.status === 401) {
    window.location.href = "/login.html";
    throw new Error("unauthorized");
  }
  return res;
}

// Verifies the signed-in user is an admin, redirects non-admins away, hides
// [data-super-admin-only] elements from plain admins, and fills in the nav's
// name/role tag. Every admin page calls this before rendering anything else.
async function requireAdmin() {
  const res = await apiFetch("/api/me");
  const me = await res.json();
  if (me.role !== "admin" && me.role !== "super_admin") {
    window.location.href = "/viewer.html";
    throw new Error("not an admin");
  }
  if (me.role !== "super_admin") {
    document.querySelectorAll("[data-super-admin-only]").forEach((el) => el.classList.add("hidden"));
  }
  const roleTag = document.getElementById("nav-role");
  if (roleTag) roleTag.textContent = `${me.display_name} - ${me.role.replace("_", " ")}`;
  markActiveNav();
  return me;
}

function markActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll("nav.admin-nav a").forEach((a) => {
    if (a.getAttribute("href") === path) a.classList.add("active");
  });
}

async function logout() {
  await apiFetch("/api/logout", { method: "POST" });
  window.location.href = "/login.html";
}

function showMsg(el, text, isError) {
  el.textContent = text;
  el.className = "msg " + (isError ? "error" : "ok");
}

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function daysOfWeekToLabel(mask) {
  return DAY_LABELS.filter((_, i) => mask & (1 << i)).join(" ") || "-";
}
