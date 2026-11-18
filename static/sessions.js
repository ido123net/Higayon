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

  async function sync() {
    if (syncing) return;
    syncing = true;
    try {
      const remote = await sessionApi(`${id}/`);
      counts = remote.counts;
      if (!remote.invite_active) $('session-sharing').hidden = true;
      let changed = mergeOwn(remote.own);
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
      if (changes.length) {
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
      syncMessage(conflict ? 'תשובה השתנתה במכשיר אחר. הטיוטה המקומית נשמרה. כדי לסנכרן אותה, יש לערוך את ההגדרה שוב.' : '');
    } catch (error) {
      syncMessage(error.status === 409 ? 'תשובה השתנתה במכשיר אחר. הגרסה תיבדק בסנכרון הבא.' :
        `${error.message} הסנכרון ינסה שוב בעוד עשר שניות.`);
    } finally {
      syncing = false;
      paint();
    }
  }

  return {
    async load() {
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
      $('solve-together').hidden = true;
      $('session-sharing').hidden = !(state.can_manage && state.invite_active);
      $('invite-link').value = state.invite_url || '';
      setInterval(sync, 10000);
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
