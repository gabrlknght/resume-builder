/* -----------------------------------------------------------
   Resume Customizer — app.js
   Tab switching, dynamic arrays, form serialization,
   pdf.js preview, API calls for generate & save.
   ----------------------------------------------------------- */

// ---------------------------------------------------------------------------
// State — hydrated from server-rendered window.__DATA__
// ---------------------------------------------------------------------------
const state = JSON.parse(JSON.stringify(window.__DATA__));

// PDF preview state
let pdfBlob = null;
let pdfDoc = null;
let currentPage = 1;
let totalPages = 0;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    populateScalarFields();
    renderEducation();
    renderExperience();
    renderProjects();
    initTabs();
});

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
function initTabs() {
    const btns = document.querySelectorAll("#sidebar button");
    btns.forEach((btn) => {
        btn.addEventListener("click", () => {
            btns.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
            document.getElementById("section-" + btn.dataset.tab).classList.add("active");
        });
    });
}

// ---------------------------------------------------------------------------
// Scalar fields — Profile & Contact (data-path driven)
// ---------------------------------------------------------------------------
function populateScalarFields() {
    document.querySelectorAll("[data-path]").forEach((el) => {
        const val = getNestedValue(state, el.dataset.path);
        if (val !== undefined && val !== null) {
            el.value = val;
        }
        el.addEventListener("input", () => {
            setNestedValue(state, el.dataset.path, el.value);
        });
    });
}

function getNestedValue(obj, path) {
    return path.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), obj);
}

function setNestedValue(obj, path, value) {
    const keys = path.split(".");
    let cur = obj;
    for (let i = 0; i < keys.length - 1; i++) {
        if (cur[keys[i]] === undefined) cur[keys[i]] = {};
        cur = cur[keys[i]];
    }
    cur[keys[keys.length - 1]] = value;
}

// ---------------------------------------------------------------------------
// Education
// ---------------------------------------------------------------------------
function renderEducation() {
    const list = document.getElementById("education-list");
    list.innerHTML = "";
    const edu = state.education || (state.education = { education: [] });
    const items = edu.education || (edu.education = []);

    items.forEach((entry, i) => {
        list.appendChild(createEducationEntry(entry, i));
    });
}

function createEducationEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";
    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeEducation(${index})">REMOVE</button>
        </div>
        <div class="field-row">
            <div class="field">
                <label>INSTITUTION</label>
                <input type="text" value="${esc(entry.institution || "")}" data-edu="${index}" data-key="institution">
            </div>
            <div class="field">
                <label>LOCATION</label>
                <input type="text" value="${esc(entry.location || "")}" data-edu="${index}" data-key="location">
            </div>
        </div>
        <div class="field">
            <label>DEGREE</label>
            <input type="text" value="${esc(entry.degree || "")}" data-edu="${index}" data-key="degree">
        </div>
        <div class="field">
            <label>DURATION</label>
            <input type="text" value="${esc(entry.duration || "")}" data-edu="${index}" data-key="duration">
        </div>
    `;
    div.querySelectorAll("input").forEach((inp) => {
        inp.addEventListener("input", () => {
            const idx = parseInt(inp.dataset.edu);
            state.education.education[idx][inp.dataset.key] = inp.value;
        });
    });
    return div;
}

function addEducation() {
    if (!state.education) state.education = { education: [] };
    if (!state.education.education) state.education.education = [];
    state.education.education.push({ institution: "", location: "", degree: "", duration: "" });
    renderEducation();
}

function removeEducation(index) {
    state.education.education.splice(index, 1);
    renderEducation();
}

// ---------------------------------------------------------------------------
// Experience
// ---------------------------------------------------------------------------
function renderExperience() {
    const list = document.getElementById("experience-list");
    list.innerHTML = "";
    const exp = state.experience || (state.experience = { experience: [] });
    const items = exp.experience || (exp.experience = []);

    items.forEach((entry, i) => {
        list.appendChild(createExperienceEntry(entry, i));
    });
}

function createExperienceEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";

    const details = entry.details || [];
    const detailsHtml = details
        .map(
            (d, di) => `
        <div class="detail-item">
            <textarea data-exp="${index}" data-detail="${di}">${esc(d)}</textarea>
            <button type="button" class="btn-danger btn-small" onclick="removeDetail(${index}, ${di})">×</button>
        </div>`
        )
        .join("");

    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeExperience(${index})">REMOVE</button>
        </div>
        <div class="field-row">
            <div class="field">
                <label>COMPANY</label>
                <input type="text" value="${esc(entry.company || "")}" data-exp-field="${index}" data-key="company">
            </div>
            <div class="field">
                <label>ROLE</label>
                <input type="text" value="${esc(entry.role || "")}" data-exp-field="${index}" data-key="role">
            </div>
        </div>
        <div class="field-row">
            <div class="field">
                <label>START DATE</label>
                <input type="text" value="${esc(entry.startDate || "")}" data-exp-field="${index}" data-key="startDate" placeholder="YYYY-MM">
            </div>
            <div class="field">
                <label>END DATE</label>
                <input type="text" value="${esc(entry.endDate || "")}" data-exp-field="${index}" data-key="endDate" placeholder="YYYY-MM OR EMPTY">
            </div>
        </div>
        <div class="field">
            <label>LOCATION</label>
            <input type="text" value="${esc(entry.location || "")}" data-exp-field="${index}" data-key="location">
        </div>
        <div class="field-group">
            <div class="field-group-title">DETAIL BULLETS</div>
            <div id="details-${index}">${detailsHtml}</div>
            <button type="button" class="btn-secondary btn-small" onclick="addDetail(${index})">+ ADD BULLET</button>
        </div>
    `;

    div.querySelectorAll("[data-exp-field]").forEach((inp) => {
        inp.addEventListener("input", () => {
            const idx = parseInt(inp.dataset.expField);
            const key = inp.dataset.key;
            const val = inp.value;
            state.experience.experience[idx][key] = val === "" && key === "endDate" ? null : val;
        });
    });

    div.querySelectorAll("[data-detail]").forEach((ta) => {
        ta.addEventListener("input", () => {
            const ei = parseInt(ta.dataset.exp);
            const di = parseInt(ta.dataset.detail);
            state.experience.experience[ei].details[di] = ta.value;
        });
    });

    return div;
}

function addExperience() {
    if (!state.experience) state.experience = { experience: [] };
    if (!state.experience.experience) state.experience.experience = [];
    state.experience.experience.push({
        company: "",
        role: "",
        startDate: "",
        endDate: null,
        location: "",
        details: [],
    });
    renderExperience();
}

function removeExperience(index) {
    state.experience.experience.splice(index, 1);
    renderExperience();
}

function addDetail(expIndex) {
    state.experience.experience[expIndex].details.push("");
    renderExperience();
}

function removeDetail(expIndex, detailIndex) {
    state.experience.experience[expIndex].details.splice(detailIndex, 1);
    renderExperience();
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------
function renderProjects() {
    const list = document.getElementById("projects-list");
    list.innerHTML = "";
    const proj = state.projects || (state.projects = { projects: [] });
    const items = proj.projects || (proj.projects = []);

    items.forEach((entry, i) => {
        list.appendChild(createProjectEntry(entry, i));
    });
}

function createProjectEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";

    const techs = entry.technologies || [];
    const techTagsHtml = techs
        .map(
            (t, ti) =>
                `<span class="tech-tag">${esc(t)}<button type="button" onclick="removeTech(${index}, ${ti})">×</button></span>`
        )
        .join("");

    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeProject(${index})">REMOVE</button>
        </div>
        <div class="field">
            <label>TITLE</label>
            <input type="text" value="${esc(entry.title || "")}" data-proj-field="${index}" data-key="title">
        </div>
        <div class="field">
            <label>DESCRIPTION</label>
            <textarea data-proj-field="${index}" data-key="description">${esc(entry.description || "")}</textarea>
        </div>
        <div class="field">
            <label>STATUS</label>
            <input type="text" value="${esc(entry.status || "")}" data-proj-field="${index}" data-key="status">
        </div>
        <div class="field-group">
            <div class="field-group-title">TECHNOLOGIES</div>
            <div class="tech-tags" id="techs-${index}">${techTagsHtml}</div>
            <div class="tech-add">
                <input type="text" id="tech-input-${index}" placeholder="Add technology">
                <button type="button" class="btn-secondary btn-small" onclick="addTech(${index})">ADD</button>
            </div>
        </div>
    `;

    div.querySelectorAll("[data-proj-field]").forEach((el) => {
        el.addEventListener("input", () => {
            const idx = parseInt(el.dataset.projField);
            state.projects.projects[idx][el.dataset.key] = el.value;
        });
    });

    const techInput = div.querySelector(`#tech-input-${index}`);
    if (techInput) {
        techInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                addTech(index);
            }
        });
    }

    return div;
}

function addProject() {
    if (!state.projects) state.projects = { projects: [] };
    if (!state.projects.projects) state.projects.projects = [];
    state.projects.projects.push({
        title: "",
        description: "",
        technologies: [],
        status: "ongoing",
    });
    renderProjects();
}

function removeProject(index) {
    state.projects.projects.splice(index, 1);
    renderProjects();
}

function addTech(projIndex) {
    const input = document.getElementById("tech-input-" + projIndex);
    const val = input.value.trim();
    if (!val) return;
    state.projects.projects[projIndex].technologies.push(val);
    input.value = "";
    renderProjects();
}

function removeTech(projIndex, techIndex) {
    state.projects.projects[projIndex].technologies.splice(techIndex, 1);
    renderProjects();
}

// ---------------------------------------------------------------------------
// Payload
// ---------------------------------------------------------------------------
function collectPayload() {
    return {
        profile: state.profile || {},
        contact: state.contact || {},
        education: state.education || { education: [] },
        experience: state.experience || { experience: [] },
        projects: state.projects || { projects: [] },
    };
}

// ---------------------------------------------------------------------------
// API: Generate → Preview + Download
// ---------------------------------------------------------------------------
async function generatePDF() {
    const btn = document.getElementById("btn-generate");
    btn.classList.add("loading");
    btn.textContent = "GENERATING…";

    try {
        const res = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(collectPayload()),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Generation failed");
        }

        pdfBlob = await res.blob();

        // Extract filename from header
        const disposition = res.headers.get("content-disposition") || "";
        const match = disposition.match(/filename="?([^"]+)"?/);
        pdfBlob._filename = match ? match[1] : "resume.pdf";

        // Render in preview pane
        await renderPDFPreview(pdfBlob);
        toast("PDF GENERATED");
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "GENERATE";
    }
}

// ---------------------------------------------------------------------------
// PDF.js Preview Rendering
// ---------------------------------------------------------------------------
async function renderPDFPreview(blob) {
    const pdfjsLib = await import("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs");
    pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs";

    const arrayBuffer = await blob.arrayBuffer();
    pdfDoc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    totalPages = pdfDoc.numPages;
    currentPage = 1;

    // Show page nav
    const nav = document.getElementById("page-nav");
    if (nav) nav.style.display = "flex";
    
    const empty = document.getElementById("preview-empty");
    if (empty) empty.style.display = "none";

    // Render all pages
    const container = document.getElementById("preview-body");
    container.innerHTML = "";

    for (let i = 1; i <= totalPages; i++) {
        const page = await pdfDoc.getPage(i);
        const scale = 1.5;
        const viewport = page.getViewport({ scale });

        const canvas = document.createElement("canvas");
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.id = "pdf-page-" + i;
        container.appendChild(canvas);

        const ctx = canvas.getContext("2d");
        await page.render({ canvasContext: ctx, viewport }).promise;
    }

    updatePageIndicator();
}

function updatePageIndicator() {
    document.getElementById("page-indicator").textContent = `${currentPage} / ${totalPages}`;
}

function prevPage() {
    if (currentPage <= 1) return;
    currentPage--;
    scrollToPage(currentPage);
    updatePageIndicator();
}

function nextPage() {
    if (currentPage >= totalPages) return;
    currentPage++;
    scrollToPage(currentPage);
    updatePageIndicator();
}

function scrollToPage(num) {
    const canvas = document.getElementById("pdf-page-" + num);
    if (canvas) canvas.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------------
// Download PDF
// ---------------------------------------------------------------------------
function downloadPDF() {
    if (!pdfBlob) return;
    const url = URL.createObjectURL(pdfBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = pdfBlob._filename || "resume.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// API: Save to Backend
// ---------------------------------------------------------------------------
async function saveToBackend() {
    const btn = document.getElementById("btn-save");
    btn.classList.add("loading");
    btn.textContent = "SAVING…";

    try {
        const res = await fetch("/api/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(collectPayload()),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Save failed");
        }

        toast("SAVED TO BACKEND");
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "SAVE TO BACKEND";
    }
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function toast(msg, isError = false) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "toast visible" + (isError ? " error" : "");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => {
        el.className = "toast";
    }, 2500);
}

// ---------------------------------------------------------------------------
// Util
// ---------------------------------------------------------------------------
function esc(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}
