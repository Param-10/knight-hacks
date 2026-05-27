const form = document.querySelector("#matter-form");
const input = document.querySelector("#matter-input");
const clearButton = document.querySelector("#clear-btn");
const sendButton = document.querySelector("#send-btn");
const chatThread = document.querySelector("#chat-thread");
const modelChip = document.querySelector("#model-chip");
const runtimeChip = document.querySelector("#runtime-chip");
const agentPills = document.querySelectorAll("[data-agent-step]");

const fields = {
  priority: document.querySelector("#priority-badge"),
  caseType: document.querySelector("#case-type"),
  confidence: document.querySelector("#confidence"),
  urgency: document.querySelector("#urgency"),
  summary: document.querySelector("#case-summary"),
  questions: document.querySelector("#question-list"),
  attorneys: document.querySelector("#attorney-list"),
  trace: document.querySelector("#trace-list"),
};

const sampleMatters = [
  "I was hit by a rideshare driver in Orlando and my neck has been hurting for three days.",
  "I got a DUI citation after a traffic stop, and my first court date is next week.",
  "My employer fired me after I reported harassment and I still have the emails.",
];

function escapeText(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function createMessage(role, text, options = {}) {
  const item = document.createElement("li");
  item.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;

  if (options.loading) {
    item.classList.add("loading-message");
    item.innerHTML = `
      <div class="skeleton-line wide"></div>
      <div class="skeleton-line"></div>
      <div class="skeleton-line short"></div>
    `;
  } else {
    const paragraph = document.createElement("p");
    paragraph.textContent = text;
    item.appendChild(paragraph);
  }

  chatThread.appendChild(item);
  chatThread.scrollTo({ top: chatThread.scrollHeight, behavior: "smooth" });
  return item;
}

function setBusy(isBusy) {
  sendButton.disabled = isBusy;
  clearButton.disabled = isBusy;
  input.disabled = isBusy;
  sendButton.textContent = isBusy ? "Reviewing" : "Review matter";
  agentPills.forEach((pill) => pill.classList.toggle("is-running", isBusy));
}

function setAgentTrace(trace = []) {
  const completed = new Set(trace.map((step) => step.name));

  agentPills.forEach((pill) => {
    const name = pill.dataset.agentStep;
    pill.classList.toggle("is-complete", completed.has(name));
    pill.classList.remove("is-running");
  });
}

function renderBrief(data) {
  const assessment = data.case_assessment || {};
  const triage = data.triage || {};
  const confidence = Number(assessment.confidence || 0);

  fields.priority.textContent = triage.intake_priority || "Standard";
  fields.priority.dataset.priority = triage.intake_priority || "standard";
  fields.caseType.textContent = assessment.case_type || "Unknown";
  fields.confidence.textContent = confidence ? `${Math.round(confidence * 100)}%` : "--";
  fields.urgency.textContent = assessment.urgency || "--";
  fields.summary.textContent = assessment.summary || "No summary returned.";
}

function renderQuestions(data) {
  const questions = data.triage?.next_questions || [];
  const flags = data.triage?.risk_flags || [];

  if (!questions.length && !flags.length) {
    fields.questions.innerHTML = "<li>No open questions yet.</li>";
    return;
  }

  const questionItems = questions
    .map((question) => `<li>${escapeText(question)}</li>`)
    .join("");
  const flagItems = flags
    .map((flag) => `<li class="risk-flag">${escapeText(flag)}</li>`)
    .join("");

  fields.questions.innerHTML = `${questionItems}${flagItems}`;
}

function renderAttorneys(data) {
  const attorneys = data.recommended_lawyers || [];

  if (!attorneys.length) {
    fields.attorneys.innerHTML = '<p class="muted-copy">No attorney match yet.</p>';
    return;
  }

  fields.attorneys.innerHTML = attorneys
    .map((attorney) => {
      const expertise = (attorney.expertise || [])
        .map((item) => `<span>${escapeText(item)}</span>`)
        .join("");
      const languages = (attorney.languages || []).join(", ");

      return `
        <article class="attorney-card">
          <div class="attorney-card-top">
            <div>
              <h3>${escapeText(attorney.name)}</h3>
              <p>${escapeText(attorney.role)} · ${escapeText(attorney.location)}</p>
            </div>
            <strong>${escapeText(attorney.match_score)}%</strong>
          </div>
          <p>${escapeText(attorney.reason)}</p>
          <div class="tag-row">${expertise}</div>
          <dl>
            <div>
              <dt>Experience</dt>
              <dd>${escapeText(attorney.experience)} years</dd>
            </div>
            <div>
              <dt>Languages</dt>
              <dd>${escapeText(languages)}</dd>
            </div>
          </dl>
          <div class="contact-row">
            <a href="mailto:${escapeText(attorney.email)}">${escapeText(attorney.email)}</a>
            <a href="tel:${escapeText(attorney.phone)}">${escapeText(attorney.phone)}</a>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderTrace(data) {
  const trace = data.agent_trace || [];

  if (!trace.length) {
    fields.trace.innerHTML = "<li>Ready.</li>";
    return;
  }

  fields.trace.innerHTML = trace
    .map(
      (step) => `
        <li>
          <span>${escapeText(step.name)}</span>
          <p>${escapeText(step.summary)}</p>
          <small>${escapeText(step.status)}</small>
        </li>
      `
    )
    .join("");
}

function renderResponse(data) {
  renderBrief(data);
  renderQuestions(data);
  renderAttorneys(data);
  renderTrace(data);
  setAgentTrace(data.agent_trace || []);
}

async function sendMatter(message) {
  createMessage("user", message);
  const loading = createMessage("assistant", "", { loading: true });
  setBusy(true);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Review failed.");
    }

    loading.remove();
    createMessage("assistant", data.reply || "No response returned.");
    renderResponse(data);
  } catch (error) {
    loading.remove();
    createMessage("assistant", error.message || "Connection failed. Please try again.");
  } finally {
    setBusy(false);
    input.focus();
  }
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    modelChip.textContent = data.model || "Gemini 3.5 Flash";
    runtimeChip.textContent = data.gemini_configured ? "Gemini connected" : "Local fallback";
    runtimeChip.classList.toggle("muted", !data.gemini_configured);
  } catch {
    runtimeChip.textContent = "Backend offline";
    runtimeChip.classList.add("error-chip");
  }
}

function mountSampleMatters() {
  const wrapper = document.createElement("div");
  wrapper.className = "sample-row";
  wrapper.setAttribute("aria-label", "Sample matters");

  sampleMatters.forEach((matter) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sample-button";
    button.textContent = matter;
    button.addEventListener("click", () => {
      input.value = matter;
      input.focus();
    });
    wrapper.appendChild(button);
  });

  form.insertAdjacentElement("beforebegin", wrapper);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  sendMatter(message);
});

clearButton.addEventListener("click", () => {
  input.value = "";
  input.focus();
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    form.requestSubmit();
  }
});

mountSampleMatters();
loadHealth();
