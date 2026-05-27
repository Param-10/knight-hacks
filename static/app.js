const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const form = document.querySelector("#matter-form");
const input = document.querySelector("#matter-input");
const clearButton = document.querySelector("#clear-btn");
const sendButton = document.querySelector("#send-btn");
const formStatus = document.querySelector("#form-status");
const agentPills = document.querySelectorAll("[data-agent-step]");

const fields = {
  priority: document.querySelector("#priority-badge"),
  caseType: document.querySelector("#case-type"),
  confidence: document.querySelector("#confidence"),
  urgency: document.querySelector("#urgency"),
  summary: document.querySelector("#case-summary"),
  response: document.querySelector("#response-text"),
  trace: document.querySelector("#trace-list"),
  reviews: document.querySelector("#review-list"),
  runtime: document.querySelector("#runtime-chip"),
  model: document.querySelector("#model-chip"),
};

function escapeText(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setView(name) {
  document.querySelectorAll("[data-view-trigger]").forEach((button) => {
    button.classList.toggle("active", button.dataset.viewTrigger === name);
  });
  document.querySelectorAll("[data-view]").forEach((view) => {
    view.classList.toggle("active", view.dataset.view === name);
  });
}

function setBusy(isBusy) {
  if (!sendButton || !clearButton || !input) return;
  sendButton.disabled = isBusy;
  clearButton.disabled = isBusy;
  input.disabled = isBusy;
  sendButton.textContent = isBusy ? "Running agents" : "Run agents";
  agentPills.forEach((pill) => {
    pill.classList.remove("is-complete", "is-error");
    pill.classList.toggle("is-running", isBusy);
  });
}

function setStatus(message, isError = false) {
  if (!formStatus) return;
  formStatus.textContent = message;
  formStatus.classList.toggle("error-text", isError);
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
  fields.response.textContent = data.reply || "No response returned.";
}

function flattenTrace(trace = []) {
  return trace.flatMap((step) => [step, ...(step.children || [])]);
}

function renderTrace(data) {
  const trace = flattenTrace(data.agent_trace || []);
  if (!trace.length) {
    fields.trace.innerHTML = "<li>Run an intake to inspect the trace.</li>";
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

function renderReviews(reviews = []) {
  if (!fields.reviews) return;
  if (!reviews.length) {
    fields.reviews.innerHTML = `
      <div class="empty-state">
        <h3>No matters yet</h3>
        <p>Run your first intake review and it will appear here.</p>
      </div>
    `;
    return;
  }
  fields.reviews.innerHTML = reviews
    .map(
      (review) => `
        <article class="review-card">
          <span>${escapeText(review.priority)}</span>
          <h3>${escapeText(review.case_type)}</h3>
          <p>${escapeText(review.summary || review.message)}</p>
          <small>${escapeText(review.created_at)}</small>
        </article>
      `
    )
    .join("");
}

async function refreshReviews() {
  if (!fields.reviews) return;
  const response = await fetch("/api/reviews");
  if (!response.ok) return;
  const data = await response.json();
  renderReviews(data.reviews || []);
}

async function loadHealth() {
  if (!fields.runtime || !fields.model) return;
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    fields.model.textContent = data.model || "Gemini";
    fields.runtime.textContent = data.last_model_error
      ? "Gemini error"
      : data.gemini_configured
        ? "Gemini connected"
        : "Gemini unavailable";
    fields.runtime.classList.toggle("error-chip", Boolean(data.last_model_error) || !data.gemini_configured);
  } catch {
    fields.runtime.textContent = "Backend unavailable";
    fields.runtime.classList.add("error-chip");
  }
}

async function submitMatter(message) {
  setBusy(true);
  setStatus("Coordinating IntakeAgent, parallel review agents, and spawned subagents.");
  try {
    const response = await fetch("/api/intake", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({ message }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Intake review failed.");
    }
    renderBrief(data);
    renderTrace(data);
    setAgentTrace(data.agent_trace || []);
    setStatus("Review complete. Matter saved to history.");
    await refreshReviews();
  } catch (error) {
    setStatus(error.message || "Intake review failed.", true);
    agentPills.forEach((pill) => {
      pill.classList.remove("is-running");
      pill.classList.add("is-error");
    });
  } finally {
    setBusy(false);
    input?.focus();
  }
}

document.querySelectorAll("[data-view-trigger]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.viewTrigger));
});

document.querySelectorAll(".sample-button").forEach((button) => {
  button.addEventListener("click", () => {
    if (!input) return;
    input.value = button.textContent.trim();
    input.focus();
  });
});

clearButton?.addEventListener("click", () => {
  input.value = "";
  setStatus("");
  input.focus();
});

form?.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (message.length < 18) {
    setStatus("Add a few more facts before running intake.", true);
    return;
  }
  submitMatter(message);
});

input?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    form.requestSubmit();
  }
});

loadHealth();
refreshReviews();
