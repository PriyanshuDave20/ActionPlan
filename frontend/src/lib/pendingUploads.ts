/**
 * Hand-off of files selected on the Home page to the workflow page.
 *
 * Project creation returns immediately (queued), so the user navigates to
 * the workflow page before documents are uploaded. File objects cannot be
 * serialized into sessionStorage, so they travel through this module-scoped
 * handoff. If the user refreshes mid-flow the handoff is lost — documents
 * are optional and can be added later from the project page.
 */

let pending: File[] = [];

export function setPendingUploads(files: File[]): void {
  pending = files;
}

export function takePendingUploads(): File[] {
  const files = pending;
  pending = [];
  return files;
}
