let token = '';
try { token = sessionStorage.getItem('agal-token') || ''; } catch { /* Browser storage is optional for public surveys. */ }
export function setToken(value) { token=value; value ? sessionStorage.setItem('agal-token',value) : sessionStorage.removeItem('agal-token'); }
export async function api(path, body, method) {
  const response = await fetch('/api'+path, {method:method || (body ? 'POST':'GET'), headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:body ? JSON.stringify(body):undefined});
  if (!response.ok) { const error = await response.json(); throw new Error(error.error || 'Request failed'); }
  return response.json();
}
export async function download(path, body, filename) {
  const response = await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(body)});
  if (!response.ok) throw new Error((await response.json()).error);
  const blob = await response.blob(), url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href=url; a.download=filename; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  const result={count:response.headers.get('X-Record-Count'),at:response.headers.get('X-Exported-At'),id:response.headers.get('X-Export-ID')};
  if(result.id) sessionStorage.setItem('agal-last-export',result.id);
  return result;
}
export async function downloadManifest() {
  const id=sessionStorage.getItem('agal-last-export');
  if(!id)throw new Error('Download a CSV first to create an export manifest.');
  const manifest=await api(`/exports/${id}/manifest`);
  const url=URL.createObjectURL(new Blob([JSON.stringify(manifest,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='survey-export-manifest.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
