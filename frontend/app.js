// The local query page (spec §6): ask, show the answer with its boards, step through them in a lightbox.
// Everything that comes from the API is inserted as text, never as HTML.

const MAX_HISTORY = 6;
const config = window.WHITEBORAG;
const turnsEl = document.getElementById("turns");
const form = document.getElementById("ask");
const input = document.getElementById("question");
const history = []; // Answered turns, as sent back to the API: {question, understood, answer, sources without image_url}.

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function shortDate(isoDate) {
  return new Date(isoDate + "T00:00:00Z").toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}

function dateTime(capturedAt) {
  return new Date(capturedAt).toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

// --- Talking to the API ---

async function query(question, project) {
  const body = { question, history: history.slice(-MAX_HISTORY) };
  if (project) body.project = project;
  const res = await fetch(config.apiUrl.replace(/\/$/, "") + "/query", {
    method: "POST",
    headers: { "content-type": "application/json", "x-api-key": config.apiKey },
    body: JSON.stringify(body),
  });
  if (res.status === 403) throw new Error("API key rejected, check config.js");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.message || `Request failed (${res.status})`);
  return data;
}

async function ask(question, slot, project) {
  form.querySelector("button").disabled = input.disabled = true;
  slot.replaceChildren(el("p", "thinking", "thinking…"));
  try {
    const data = await query(question, project);
    if (data.clarify) {
      slot.replaceChildren(renderClarify(question, data.clarify, slot));
    } else {
      slot.replaceChildren(renderAnswer(data));
      history.push({
        question,
        understood: data.understood,
        answer: data.answer,
        sources: data.sources.map(({ image_url, ...rest }) => rest),
      });
    }
  } catch (err) {
    slot.replaceChildren(el("p", "error", err.message || String(err)));
  } finally {
    form.querySelector("button").disabled = input.disabled = false;
    input.focus();
    slot.scrollIntoView({ block: "end", behavior: "smooth" });
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  const turn = el("section", "turn");
  const slot = el("div", "reply");
  turn.append(el("p", "question", question), slot);
  turnsEl.append(turn);
  ask(question, slot);
});

// --- One turn's reply ---

function renderClarify(question, clarify, slot) {
  const box = el("div", "clarify");
  box.append(el("p", null, clarify.message));
  const buttons = el("div", "options");
  for (const option of clarify.options) {
    const button = el("button", null, option.display_name);
    button.type = "button";
    button.addEventListener("click", () => ask(question, slot, option.key));
    buttons.append(button);
  }
  box.append(buttons);
  return box;
}

function renderAnswer(data) {
  const box = el("div", "answer");
  if (data.project) {
    const how = { previous: "from earlier", latest: "most recent" }[data.project.how];
    const chip = el("span", "chip", data.project.display_name);
    if (how) chip.append(el("span", "how", ` · ${how}`));
    box.append(chip);
  }
  box.append(el("p", "text", data.answer || ""));
  if (data.sources.length) {
    const row = el("div", "thumbs");
    data.sources.forEach((source, i) => row.append(renderThumb(data.sources, i)));
    box.append(row);
  }
  return box;
}

function expiredPlaceholder() {
  return el("div", "expired", "link expired, ask again");
}

function renderThumb(sources, index) {
  const source = sources[index];
  const label = [shortDate(source.date), source.project].filter(Boolean).join(" · ");
  const button = el("button", "thumb");
  button.type = "button";
  button.setAttribute("aria-label", `Open the ${label} board`);
  const img = el("img");
  img.src = source.image_url;
  img.alt = "";
  img.loading = "lazy";
  img.addEventListener("error", () => img.replaceWith(expiredPlaceholder()));
  button.append(img, el("span", "caption", label));
  button.addEventListener("click", () => openLightbox(sources, index));
  return button;
}

// --- Lightbox ---

const lightbox = document.getElementById("lightbox");
const lbImg = lightbox.querySelector("img");
const lbExpired = lightbox.querySelector(".expired");
let shown = { sources: [], index: 0 };

function showSource() {
  const { sources, index } = shown;
  const source = sources[index];
  lbExpired.hidden = true;
  lbImg.hidden = false;
  lbImg.src = source.image_url;
  lbImg.alt = `Board from ${dateTime(source.captured_at)}`;
  lightbox.querySelector(".when").textContent = dateTime(source.captured_at);
  lightbox.querySelector(".project").textContent = source.project || "untitled";
  lightbox.querySelector(".section").textContent = source.section;
  lightbox.querySelector(".count").textContent = `${index + 1} of ${sources.length}`;
  for (const nav of lightbox.querySelectorAll(".nav")) nav.hidden = sources.length < 2;
}

function step(by) {
  const n = shown.sources.length;
  shown.index = (shown.index + by + n) % n;
  showSource();
}

function openLightbox(sources, index) {
  shown = { sources, index };
  showSource();
  lightbox.showModal();
}

lbImg.addEventListener("error", () => {
  lbImg.hidden = true;
  lbExpired.hidden = false;
});
lightbox.querySelector(".prev").addEventListener("click", () => step(-1));
lightbox.querySelector(".next").addEventListener("click", () => step(1));
lightbox.querySelector(".close").addEventListener("click", () => lightbox.close());
lightbox.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") step(-1);
  if (event.key === "ArrowRight") step(1);
});

// closedby="any" closes on a backdrop click; Safari doesn't support it yet, so do it by hand there.
if (!("closedBy" in HTMLDialogElement.prototype)) {
  lightbox.addEventListener("click", (event) => {
    if (event.target !== lightbox) return;
    const r = lightbox.getBoundingClientRect();
    const inside = r.top <= event.clientY && event.clientY <= r.bottom && r.left <= event.clientX && event.clientX <= r.right;
    if (!inside) lightbox.close();
  });
}

// --- Start ---

if (!config || !config.apiUrl || !config.apiKey) {
  turnsEl.append(el("p", "error", "Missing config.js: copy config.example.js to config.js and fill in apiUrl and apiKey."));
  form.querySelector("button").disabled = input.disabled = true;
} else {
  input.focus();
}
