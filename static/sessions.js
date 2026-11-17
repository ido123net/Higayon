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
    throw new Error('אין חיבור לשרת. הטיוטה נשמרה מקומית; יש ללחוץ שוב כדי לשלוח.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || 'לא ניתן להשלים את הפעולה. יש לנסות שוב.');
    error.status = response.status;
    throw error;
  }
  return data;
}

// This controller never uploads from input, timers, pagehide, or storage events.
export function sharedSession(id, message) {
  let state, own = {}, counts = {}, slots = [], getValues, save, paint;
  let dialogResolve = null, busy = false, disposed = false, polling = false, lastError = '';
  const $ = name => document.getElementById(name);
  const dialog = $('answer-decisions');
  const word = (slot, values = getValues()) => slot.cells.map(c => values[c.join(',')] || ' ').join('');
  const complete = text => /^[א-ת]+$/.test(text);
  const dirty = () => slots.filter(s => own[key(s)]?.answer && own[key(s)].answer !== word(s));
  const change = (slot, answer) => ({direction: slot.direction, number: slot.number, answer, version: own[key(slot)]?.version || 0});
  const title = slot => `${slot.number} ${slot.direction === 'across' ? 'מאוזן' : 'מאונך'}`;

  async function send(changes) {
    if (busy) return false;
    busy = true;
    try {
      const result = await sessionApi(`${id}/answers/`, {method: 'POST', body: JSON.stringify({changes})});
      Object.assign(own, result.own);
      return true;
    } catch (e) {
      if (e.status === 409) {
        // Refresh versions, preserving every local letter. A second explicit click is required.
        try { own = (await sessionApi(`${id}/`)).own; } catch { /* keep previous baseline */ }
      }
      lastError = e.message;
      message(e.message);
      $('decision-error').textContent = e.message;
      return false;
    } finally {
      busy = false;
      paint?.();
    }
  }

  function finish(value) {
    dialog.close();
    const resolve = dialogResolve;
    dialogResolve = null;
    if (!value) $('entry').focus({preventScroll: true});
    resolve?.(value);
  }
  $('decisions-cancel').addEventListener('click', () => { if (!busy) finish(false); });
  dialog.addEventListener('cancel', e => { e.preventDefault(); if (!busy) finish(false); });

  function renderDecisions() {
    $('decision-list').replaceChildren();
    $('decision-error').textContent = '';
    for (const slot of dirty()) {
      const row = document.createElement('label');
      row.className = 'decision-row';
      const text = document.createElement('span');
      const isComplete = complete(word(slot));
      text.textContent = `${title(slot)}: ${isComplete ? 'להחליף לתשובה החדשה?' : 'לבטל את התשובה הקודמת?'}`;
      const select = document.createElement('select');
      select.dataset.clue = key(slot);
      select.add(new Option('יש לבחור פעולה', ''));
      select.add(new Option(isComplete ? 'החלפה לתשובה החדשה' : 'ביטול האישור הקודם', 'submit'));
      select.add(new Option('שחזור התשובה המאושרת', 'restore'));
      row.append(text, select);
      $('decision-list').append(row);
    }
  }

  $('decisions-apply').addEventListener('click', async () => {
    if (busy) return;
    const pending = dirty();
    const selections = [...document.querySelectorAll('#decision-list select')];
    if (selections.some(s => !s.value)) {
      $('decision-error').textContent = 'יש לבחור פעולה לכל הגדרה, או לחזור לעריכה.';
      return;
    }
    const next = {...getValues()}, changes = [];
    for (const slot of pending) {
      if (selections.find(s => s.dataset.clue === key(slot))?.value === 'restore') {
        [...own[key(slot)].answer].forEach((letter, i) => { next[slot.cells[i].join(',')] = letter; });
      }
    }
    if (pending.some(slot => selections.find(s => s.dataset.clue === key(slot))?.value === 'restore' && word(slot, next) !== own[key(slot)].answer)) {
      $('decision-error').textContent = 'התשובות המאושרות סותרות זו את זו באות מצטלבת. יש לחזור לעריכה ולאשר תשובה מתוקנת.';
      return;
    }
    for (const slot of pending) {
      const action = selections.find(s => s.dataset.clue === key(slot))?.value;
      if (action === 'submit') {
        if (word(slot, next) !== word(slot)) {
          $('decision-error').textContent = 'השחזור משנה אותיות בתשובה אחרת שבחרת לשלוח. יש לחזור לעריכה ולהכריע באותיות המצטלבות.';
          return;
        }
        changes.push(change(slot, complete(word(slot)) ? word(slot) : null));
      }
    }
    // Restoring crossing words must not silently change another confirmed answer.
    if (slots.some(s => own[key(s)]?.answer && !pending.includes(s) && word(s, next) !== own[key(s)].answer)) {
      $('decision-error').textContent = 'השחזור משפיע על הגדרה מאושרת נוספת. יש לחזור לעריכה.';
      return;
    }
    $('decisions-apply').disabled = true;
    if (!changes.length || await send(changes)) {
      Object.keys(getValues()).forEach(k => delete getValues()[k]);
      Object.assign(getValues(), next);
      save();
      finish(true);
    } else {
      renderDecisions();
      $('decision-error').textContent = lastError;
    }
    $('decisions-apply').disabled = false;
  });

  async function poll() {
    if (disposed || polling || document.hidden) return;
    polling = true;
    try {
      const result = await sessionApi(`${id}/`);
      if (disposed) return;
      counts = result.counts;
      if (!result.invite_active) $('session-sharing').hidden = true;
      paint?.();
    } catch (e) { if (!disposed) message(e.message); }
    finally { polling = false; }
  }
  const timer = setInterval(poll, 10000);
  document.addEventListener('visibilitychange', poll);

  return {
    async load() {
      state = await sessionApi(`${id}/`);
      own = state.own;
      counts = state.counts;
      return state;
    },
    attach(templateSlots, values, persist, repaint, hasDraft) {
      slots = templateSlots; getValues = values; save = persist; paint = repaint;
      if (!hasDraft) {
        // Use own confirmed answers on a new device; existing drafts, including deletions, win.
        for (const slot of slots) {
          const answer = own[key(slot)]?.answer;
          if (answer) [...answer].forEach((letter, i) => {
            const coord = slot.cells[i].join(',');
            if (!(coord in getValues())) getValues()[coord] = letter;
          });
        }
        save();
      }
      $('session-controls').hidden = false;
      $('solve-together').hidden = true;
      $('session-sharing').hidden = !(state.can_manage && state.invite_active);
      $('invite-link').value = state.invite_url || '';
    },
    count(slot) { return `${counts[key(slot)] || 0} משתתפים אחרים אישרו`; },
    paint(active, clueEls) {
      for (const slot of slots) {
        const badge = clueEls.get(key(slot))?.querySelector('.answer-count');
        if (badge) badge.textContent = this.count(slot);
      }
      if (!active) return;
      $('active-count').textContent = this.count(active);
      const answer = word(active), previous = own[key(active)]?.answer;
      $('confirm-answer').disabled = busy || !complete(answer) || previous === answer;
      $('confirm-answer').textContent = previous && previous !== answer ? 'אישור התשובה החדשה' : 'אישור התשובה';
      $('confirmation-state').textContent = previous === answer ? 'התשובה אושרה' : previous ? 'שינויים מקומיים שטרם אושרו' : 'טרם אושרה תשובה';
    },
    async confirm(slot) {
      if (!complete(word(slot))) return;
      if (await send([change(slot, word(slot))])) message('התשובה אושרה.');
    },
    guard() {
      if (!dirty().length) return Promise.resolve(true);
      if (dialogResolve) return Promise.resolve(false);
      renderDecisions();
      dialog.showModal();
      return new Promise(resolve => { dialogResolve = resolve; });
    },
    hasPending: () => getValues && dirty().length > 0,
    async revoke() {
      try {
        await sessionApi(`${id}/revoke/`, {method: 'POST'});
        $('session-sharing').hidden = true;
        message('קישור ההצטרפות בוטל. המשתתפים הקיימים נשארו במפגש.');
      } catch (e) { message(e.message); }
    },
    dispose() { disposed = true; clearInterval(timer); document.removeEventListener('visibilitychange', poll); }
  };
}
