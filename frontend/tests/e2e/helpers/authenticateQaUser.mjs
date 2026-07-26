import { readFile } from 'node:fs/promises';

export async function authenticateQaUser(page, credentialsPath, storageStatePath) {
  let credentials;
  try { credentials = JSON.parse(await readFile(credentialsPath, 'utf8')); }
  catch { throw new Error('QA_CREDENTIAL_LOAD: unavailable runtime credentials'); }
  try {
    const result = await page.evaluate(async ({ phone, password }) => {
      const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone, password }) });
      if (!response.ok) throw new Error(`LOGIN_REQUEST: ${response.status}`);
      const body = await response.json();
      if (!body.access_token || !body.refresh_token) throw new Error('AUTH_RESPONSE: incomplete response');
      localStorage.setItem('edu_token', body.access_token);
      localStorage.setItem('r436_refresh_token', body.refresh_token);
      const me = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${body.access_token}` } });
      if (!me.ok) throw new Error(`AUTH_ME_VERIFY: ${me.status}`);
      return (await me.json()).learner?.id || '';
    }, credentials);
    if (!result) throw new Error('AUTH_ME_VERIFY: missing learner');
    await page.context().storageState({ path: storageStatePath });
    return result;
  } catch (error) {
    throw new Error(String(error?.message || error).match(/^(LOGIN_REQUEST|AUTH_RESPONSE|AUTH_ME_VERIFY)/)?.[0] || `LOGIN_REQUEST: ${String(error?.message || error)}`);
  }
}
