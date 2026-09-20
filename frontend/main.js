const list = document.getElementById("list");
const detail = document.getElementById("detail");
const back = document.getElementById("back");
const dTitle = document.getElementById("d-title");
const dMeta  = document.getElementById("d-meta");
const dBody  = document.getElementById("d-body");
const catsDiv = document.getElementById("cats");
const priceBar = document.getElementById("price-bar");

let allArticles = [];

async function loadAll() {
  const res = await fetch("/api/articles");
  allArticles = await res.json();
  makeCatButtons();
  showCategory("all");
}

function makeCatButtons() {
  catsDiv.innerHTML = "";
  const cats = ["all", ...new Set(allArticles.map(a => a.category))];
  cats.forEach(c => {
    const btn = document.createElement("button");
    btn.textContent = c.charAt(0).toUpperCase() + c.slice(1);
    btn.onclick = () => showCategory(c);
    catsDiv.appendChild(btn);
  });
}

function showCategory(cat) {
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

async function showDetail(id) {
  detail.style.display = "block";
  list.innerHTML = "";
  try {
    const res = await fetch(`/api/article/${id}`);
    if (!res.ok) throw new Error("Article not found");
    const art = await res.json();
    dTitle.textContent = art.title;
    dMeta.textContent = `By ${(art.authors || []).join(", ")} — ${art.published}`;
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

window.onpopstate = () => {
  if (window.location.pathname.startsWith("/article/")) {
    const id = window.location.pathname.split("/article/")[1];
    showDetail(id);
  } else {
    detail.style.display = "none";
    loadAll();
  }
};

async function loadLivePrices() {
  if (!priceBar) return;
  try {
    const metalRes = await fetch("https://api.metals.live/v1/spot");
    const metalData = await metalRes.json();
    const prices = {};
    metalData.forEach(item => {
      prices[item[0]] = item[1];
    });

    const gold = prices.gold ? `$${prices.gold.toFixed(2)}` : "N/A";
    const silver = prices.silver ? `$${prices.silver.toFixed(2)}` : "N/A";

    const stockRes = await fetch("https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d");
    const stockJson = await stockRes.json();
    const applePrice = stockJson.chart.result[0].meta.regularMarketPrice;
    const apple = applePrice ? `$${applePrice.toFixed(2)}` : "N/A";

    priceBar.innerHTML = `📈 Apple: <b>${apple}</b> | 🪙 Gold: <b>${gold}</b> | 🥈 Silver: <b>${silver}</b>`;
  } catch (e) {
    priceBar.textContent = "Live prices unavailable";
    console.error("Error loading live prices", e);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadLivePrices();
  setInterval(loadLivePrices, 300000); // Refresh every 5 minutes

  if (window.location.pathname.startsWith("/article/")) {
    const id = window.location.pathname.split("/article/")[1];
    showDetail(id);
  } else {
    loadAll();
  }
});
