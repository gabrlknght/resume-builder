/* Global application state management */

export const state = {
  data: JSON.parse(JSON.stringify(window.__DATA__)),

  // Tailoring state
  originalSnapshot: null,
  pendingTailored: null,

  // Preview state
  currentPreviewTab: "pdf",
  lastAiResultsHTML: "",

  // PDF state
  pdfBlob: null,
  pdfDoc: null,
  currentPage: 1,
  totalPages: 0,

  // Cover letter state
  coverLetterData: null,
  lastCoverLetterHTML: "",
};

export function updateState(updates) {
  Object.assign(state, updates);
}

export function resetState() {
  state.originalSnapshot = null;
  state.pendingTailored = null;
  state.currentPreviewTab = "pdf";
  state.lastAiResultsHTML = "";
  state.pdfBlob = null;
  state.pdfDoc = null;
  state.currentPage = 1;
  state.totalPages = 0;
  state.coverLetterData = null;
  state.lastCoverLetterHTML = "";
}
