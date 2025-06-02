const list = document.getElementById("list");
const detail = document.getElementById("detail");
const back = document.getElementById("back");
const dTitle = document.getElementById("d-title");
const dMeta  = document.getElementById("d-meta");
const dBody  = document.getElementById("d-body");
const catsDiv = document.getElementById("cats");

let allArticles = [];

async function loadAll() {
  const res = await fetch("/api/articles");
  allArticles = await res.json();
  makeCatButtons();
  showCategory("all");
}

function makeCatButtons() {
  catsDiv.innerHTML = ""; // clear previous buttons
  const cats = ["all", ...new Set(allArticles.map(a => a.category))];
  cats.forEach(c => {
    const btn = document.createElement("button");
    btn.textContent = c.charAt(0).toUpperCase() + c.slice(1);
    btn.onclick = () => showCategory(c);
    catsDiv.appendChild(btn);
  });
}

function showCategory(cat){
  detail.style.display = "none";
  list.innerHTML = "";
  const ul = document.createElement("ul");
  allArticles
    .filter(a => cat === "all" || a.category === cat)
    .forEach(a => {
      const li = document.createElement("li");
      li.textContent = a.title;
      li.style.cursor = "pointer";
      li.onclick = () => {
        history.pushState(null, "", `/article/${a.id}`);
        showDetail(a.id);
      };
      ul.appendChild(li);
    });
  list.appendChild(ul);
}

async function showDetail(id){
  detail.style.display = "block";
  list.innerHTML = "";
  try {
    const res = await fetch(`/api/article/${id}`);
    if (!res.ok) throw new Error("Article not found");
    const art = await res.json();
    dTitle.textContent = art.title;
    dMeta.textContent = `By ${(art.authors||[]).join(", ")} — ${art.published}`;
    dBody.innerHTML = (art.text || "").replace(/\n/g, "<br>");
  } catch {
    dTitle.textContent = "Error loading article";
    dMeta.textContent = "";
    dBody.textContent = "";
  }
}

back.onclick = () => {
  history.pushState(null, "", "/");
  detail.style.display = "none";
  loadAll();
};

// Handle browser back/forward buttons
window.onpopstate = () => {
  if (window.location.pathname.startsWith("/article/")) {
    const id = window.location.pathname.split("/article/")[1];
    showDetail(id);
  } else {
    detail.style.display = "none";
    loadAll();
  }
};

// On initial page load, check URL and load accordingly
document.addEventListener("DOMContentLoaded", () => {
  if (window.location.pathname.startsWith("/article/")) {
    const id = window.location.pathname.split("/article/")[1];
    showDetail(id);
  } else {
    loadAll();
  }
});
