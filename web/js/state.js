import { jobStatusLabel } from "./i18n.js";

export { jobStatusLabel };
export const BATCH_TARGET_NEW = "__new__";
export const SELECTED_BATCH_KEY = "selected_batch_id";

export const state = {
  selectedId: null,
  pollTimer: null,
  jobs: [],
  batches: [],
  orphans: [],
  speakerKeys: [],
  ctxJobId: null,
  ctxBatchId: null,
  rulesBatchId: null,
  dragJobId: null,
  lastSpeakersError: null,
  selectedBatchId: null,
  pendingFolderPaths: [],
  pendingFolderBatchId: null,
  legacyTab: "files",
  dropTarget: "single",
};
