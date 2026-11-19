import {key} from './api.js';

export async function sessionApi(path = '', options = {}) {
  const csrf = document.cookie.split('; ').find(v => v.startsWith('csrftoken='))?.split('=')[1];
  let response;
  try {
    response = await fetch(`/api/v1/sessions/${path}`, {
      credentials: 'same-origin', ...options,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf || '', ...options.headers}
    });
  } catch {
    throw new Error('אין חיבור לשרת.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || 'לא ניתן להשלים את הפעולה. יש לנסות שוב.');
    error.status = response.status;
    throw error;
  }
  return data;
}

// Missing cells stay as spaces so a partial word can never be uploaded.
function word(slot, values) {
  return slot.cells.map(cell => values[cell.join(',')] || ' ').join('');
}

export function completedAnswer(slot, values) {
  const text = word(slot, values);
  return text.includes(' ') ? '' : text;
}

function showCount(badge, count) {
  const number = String(count ?? 0);
  const value = badge.querySelector('.count-value');
  if (value.textContent === number) return;
  value.textContent = number;
  const label = `מספר המשתתפים האחרים שהשלימו את ההגדרה: ${number}`;
  badge.setAttribute('aria-label', label);
  badge.title = label;
}

export function sharedSession(id, message) {
  let state, slots, values, save, paint, syncing = false;
  let own = {}, counts = {}, pending = {};
  let dirty = false, writeReady = false, readNeeded = false, retryMs = 500;
  let debounce, retry;
  const live = Boolean(document.getElementById('show-roster'));
  const words = new Map();
  const $ = name => document.getElementById(name);
  const version = (records, k) => records[k]?.version || 0;

  // Keep the version an edit was based on, including across a reload or lost response.
  function edited() {
    for (const slot of slots) {
      const k = key(slot), text = word(slot, values);
      if (text === words.get(k)) continue;
      words.set(k, text);
      if (completedAnswer(slot, values) || own[k]?.answer || k in pending) {
        pending[k] = version(own, k);
        if (live) queueWrite();
      }
    }
  }

  function serverCells(records) {
    const cells = {};
    for (const slot of slots) {
      const answer = records[key(slot)]?.answer;
      if (answer) slot.cells.forEach((cell, i) => { cells[cell.join(',')] = answer[i]; });
    }
    return cells;
  }

  function mergeOwn(remote) {
    const changed = slots.some(slot => version(remote, key(slot)) !== version(own, key(slot)));
    if (!changed) return false;
    const before = serverCells(own), after = serverCells(remote);
    const protectedCells = new Set(slots.filter(s => key(s) in pending)
      .flatMap(s => s.cells.map(c => c.join(','))));
    for (const coord of new Set([...Object.keys(before), ...Object.keys(after)])) {
      if (protectedCells.has(coord) || values[coord] !== before[coord]) continue;
      if (after[coord]) values[coord] = after[coord];
      else delete values[coord];
    }
    for (const slot of slots) {
      const k = key(slot), text = word(slot, values);
      // A letter restored from this player's other device can finish a crossing draft.
      if (!(k in pending) && words.has(k) && words.get(k) !== text &&
          version(own, k) === version(remote, k) &&
          completedAnswer(slot, values) !== (remote[k]?.answer || '')) {
        pending[k] = version(remote, k);
      }
      words.set(k, text);
    }
    own = remote;
    return true;
  }

  function syncMessage(text) {
    const el = $('sync-status');
    if (el.textContent !== text) el.textContent = text;
    el.hidden = !text;
  }

  function queueWrite() {
    writeReady = false;
    clearTimeout(debounce);
    debounce = setTimeout(() => { debounce = null; writeReady = true; sync(); }, 250);
  }

  function invalidate() {
    readNeeded = true;
    sync();
  }

  async function sync() {
    if (syncing) { dirty = true; return; }
    syncing = true;
    try {
      let changed = false;
      if (readNeeded || !live) {
        readNeeded = false;
        const remote = await sessionApi(`${id}/`);
        counts = remote.counts;
        if (!remote.invite_active && $('session-sharing')) $('session-sharing').hidden = true;
        changed = mergeOwn(remote.own);
        if (changed) {
          save();
          if (live && !debounce && Object.keys(pending).length) queueWrite();
        }
      }
      if (live && !writeReady) return;
      writeReady = false;
      const changes = [];
      let conflict = false;
      for (const slot of slots) {
        const k = key(slot);
        if (!(k in pending)) continue;
        const answer = completedAnswer(slot, values);
        if (answer === (own[k]?.answer || '')) {
          delete pending[k];
          changed = true;
        } else if (pending[k] !== version(own, k)) {
          conflict = true;
        } else {
          changes.push({direction: slot.direction, number: slot.number, answer: answer || null, version: pending[k]});
        }
      }
      if (changed) save();
      if (!conflict && changes.length) {
        const result = await sessionApi(`${id}/answers/`, {method: 'POST', body: JSON.stringify({changes})});
        Object.assign(own, result.own);
        // Typing can continue during the request. Compare the live grid before retiring an edit.
        for (const slot of slots) {
          const k = key(slot), saved = result.own[k];
          if (!saved) continue;
          if (completedAnswer(slot, values) === saved.answer) delete pending[k];
          else pending[k] = saved.version;
        }
        save();
      }
      retryMs = 500;
      syncMessage(conflict ? 'תשובה השתנתה במכשיר אחר. הטיוטה המקומית נשמרה. כדי לסנכרן אותה, יש לערוך את ההגדרה שוב.' : '');
    } catch (error) {
      syncMessage(error.status === 409 ? 'תשובה השתנתה במכשיר אחר. הגרסה תיבדק בסנכרון הבא.' :
        `${error.message} הטיוטה נשמרה בדפדפן.`);
      if (live && ![401, 403, 404].includes(error.status)) {
        clearTimeout(retry);
        retry = setTimeout(() => {
          writeReady = Object.keys(pending).length > 0;
          invalidate();
        }, retryMs);
        retryMs = Math.min(retryMs * 2, 8000);
      }
    } finally {
      syncing = false;
      paint();
      if (live && dirty) { dirty = false; queueMicrotask(sync); }
    }
  }

  function startPresence(connected) {
    const button = $('show-roster'), dialog = $('roster');
    button.onclick = () => dialog.showModal();
    function disconnected(text) {
      $('presence-count').textContent = '…';
      $('presence-status').textContent = text;
      $('roster-names').replaceChildren();
      button.setAttribute('aria-label', text);
    }
    let source;
    function connect() {
      source = new EventSource(`/api/v1/sessions/${id}/events/`);
      source.addEventListener('state', () => {
        connected();
        if (slots) invalidate();
        else readNeeded = true;
      });
      source.addEventListener('presence', event => {
        const members = JSON.parse(event.data);
        button.disabled = false;
        button.setAttribute('aria-label', `מחוברים למפגש: ${members.length}`);
        $('presence-count').textContent = members.length;
        $('presence-status').textContent = '';
        $('roster-names').replaceChildren(...members.map(member => {
          const li = document.createElement('li');
          li.textContent = member.me ? `${member.name} (אני)` : member.name;
          return li;
        }));
      });
      source.onerror = () => { disconnected('החיבור נותק, מתחבר מחדש…'); connected(); };
      source.addEventListener('revoked', () => {
        source.close();
        disconnected('הגישה למפגש הסתיימה.');
      });
    }
    connect();
    window.addEventListener('pagehide', () => source.close());
    window.addEventListener('pageshow', e => { if (e.persisted) connect(); });
    window.addEventListener('online', () => { if (Object.keys(pending).length) queueWrite(); });
  }

  return {
    async load() {
      if (live) await new Promise(startPresence);
      readNeeded = false;
      state = await sessionApi(`${id}/`);
      counts = state.counts;
      return state;
    },
    attach(templateSlots, draft, savedSync, hasDraft, persist, repaint) {
      slots = templateSlots; values = draft; save = persist; paint = repaint;
      if (savedSync) {
        own = savedSync.own || {};
        pending = savedSync.pending || {};
        for (const slot of slots) words.set(key(slot), word(slot, values));
        mergeOwn(state.own);
      } else {
        own = state.own;
        if (!hasDraft) Object.assign(values, serverCells(own));
        // Upgrade legacy local grids. Missing letters alone are not a withdrawal.
        for (const slot of slots) {
          const k = key(slot), answer = completedAnswer(slot, values);
          if (answer && answer !== own[k]?.answer) pending[k] = version(own, k);
          words.set(k, word(slot, values));
        }
      }
      save();
      $('session-controls').hidden = false;
      if ($('solve-together')) $('solve-together').hidden = true;
      if ($('session-sharing')) $('session-sharing').hidden = !(state.can_manage && state.invite_active);
      if ($('invite-link')) $('invite-link').value = state.invite_url || '';
      if (live) {
        if (readNeeded) invalidate();
        if (Object.keys(pending).length) queueWrite();
      } else {
        setInterval(sync, 10000);
      }
    },
    edited,
    snapshot: () => ({own, pending}),
    paint(active, clueEls) {
      for (const slot of slots || []) {
        const badge = clueEls.get(key(slot))?.querySelector('.answer-count');
        if (badge) showCount(badge, counts[key(slot)]);
      }
      if (active) showCount($('active-count'), counts[key(active)]);
    },
    async revoke() {
      try {
        await sessionApi(`${id}/revoke/`, {method: 'POST'});
        $('session-sharing').hidden = true;
        message('קישור ההצטרפות בוטל. המשתתפים הקיימים נשארו במפגש.');
      } catch (e) { message(e.message); }
    }
  };
}
