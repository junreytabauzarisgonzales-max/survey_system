export async function deviceFiles() {
  if (!window.pywebview) return null;
  if (!window.pywebview.api) {
    await new Promise(resolve => window.addEventListener('pywebviewready', resolve, {once:true}));
  }
  return window.pywebview.api;
}

export async function saveBlob(blob, filename) {
  const device = await deviceFiles();
  if (device) {
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
    if (!await device.save_file(filename, content)) throw new Error('Save canceled.');
    return;
  }
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href=url; a.download=filename; a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}
