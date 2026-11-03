// File > Save copy, Export Figure and Export MOL: the session's document, as a
// download. An open note is committed first, as leaving it would, and a note
// that was not saved stops the download; each action runs one at a time, and a
// reply for a document since replaced, renamed, edited or busy is not its file.
// Export Figure and Export MOL clear only their own refusal, and only while that
// is still the notice shown.
//
// The page passes its live state as functions, so each check reads the state at
// that moment rather than when the actions were made.
export const SAVE_COPY_NOTICE = 'Save copy requested. Check your downloads before closing; the original file has not changed.';

export function documentDownloads({editor, isLoading, finishNoteEdit, api, download, notice, noticeSerial, selectedItems}) {
  const ready = () => editor.document && !editor.busy && !isLoading();
  function action(request, file, {confirm = null, ownRefusal = false} = {}) {
    let running = false, refusal = null;
    return async () => {
      if (running || !ready()) return;
      running = true;
      try {
        if (await finishNoteEdit() === false) return;
        if (!ready()) return;
        const {session, revision} = editor.info, name = editor.name;
        const current = () => !editor.busy && !isLoading() && editor.info?.session === session && editor.info?.revision === revision && editor.name === name;
        try {
          const reply = await api('session', {session, revision, ...request()});
          if (current()) {
            download(...file(reply, name.replace(/\.cdxml$/i, '')));
            if (confirm) notice(confirm);
            if (ownRefusal) {
              if (refusal === noticeSerial()) notice();
              refusal = null;
            }
          }
        } catch (error) {
          if (current()) {
            notice(error.message, true);
            if (ownRefusal) refusal = noticeSerial();
          }
        }
      } finally { running = false; }
    };
  }
  return {
    // The session holds embedded images; the browser's copy carries references.
    saveCopy: action(
      () => ({action: 'save_cdxml'}),
      ({cdxml}, stem) => [cdxml, `${stem}-web-copy.cdxml`, 'chemical/x-cdxml'],
      {confirm: SAVE_COPY_NOTICE}),
    exportFigure: action(
      () => ({action: 'export_figure', format: 'svg', scope: 'sheet'}),
      ({svg}, stem) => [svg, `${stem}.svg`, 'image/svg+xml'],
      {ownRefusal: true}),
    // The selection is read once the note is committed, as the request is sent.
    exportMol: action(
      () => ({action: 'export_mol', selection: selectedItems()}),
      ({molfile}, stem) => [molfile, `${stem}.mol`, 'chemical/x-mdl-molfile'],
      {ownRefusal: true}),
  };
}
