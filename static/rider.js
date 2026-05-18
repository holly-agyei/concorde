/* Rider-side Uber app — live map + ETA card. */

const $ = (s, r = document) => r.querySelector(s);

const map = UberMap.initMap('map', [37.7, -122.4], 11, { dark: false });
const route = new UberMap.RouteLayer(map, { color: '#06c167', showPickup: true });

let lastDriver = null, lastPickup = null, lastDestination = null;

function setEta(min) { $('#etaNum').textContent = String(min ?? '—'); }

function flashEta() {
  const el = $('.card__eta');
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');
}

async function bootState() {
  try {
    const res = await fetch('/api/state');
    const state = await res.json();
    const ride = state?.uber?.rides?.ride_001;
    const driver = state?.uber?.drivers?.driver_001;
    if (!ride || !driver) return;
    lastDriver = driver.current_location;
    lastPickup = ride.pickup;
    lastDestination = driver.destination;
    $('#driverName').textContent = driver.name || 'David';
    $('#driverAvatar').textContent = (driver.name || 'D')[0];
    $('#pickupLabel').textContent = ride.pickup?.label || '—';
    $('#dropLabel').textContent = driver.destination?.label || '—';
    $('#dropDoor').textContent = driver.destination?.door || '';
    setEta(driver.eta_minutes);
    route.render({ driver: lastDriver, pickup: lastPickup, destination: lastDestination });
  } catch (_) { /* noop */ }
}

function subscribe() {
  const es = new EventSource('/events');
  es.addEventListener('message', (ev) => {
    let p; try { p = JSON.parse(ev.data); } catch { return; }
    handle(p);
  });
}

let toastT = null;
function toast(text) {
  const t = $('#toast');
  t.textContent = text;
  t.hidden = false;
  if (toastT) clearTimeout(toastT);
  toastT = setTimeout(() => { t.hidden = true; }, 2400);
}

function setStatus(text, alert = false) {
  $('#statusText').textContent = text;
  $('#statusPill').classList.toggle('status-pill--alert', alert);
}

async function handle({ type, data }) {
  if (!type || !data) return;
  switch (type) {
    case 'uber_rerouted': {
      $('#dropLabel').textContent = data.to;
      $('#dropDoor').textContent = data.door || '';
      setEta(data.eta_minutes);
      flashEta();
      toast(`Route updated → ${data.to}`);
      try {
        const res = await fetch('/api/state');
        const state = await res.json();
        const driver = state?.uber?.drivers?.driver_001;
        if (driver) {
          lastDriver = driver.current_location;
          lastDestination = driver.destination;
          route.render({ driver: lastDriver, pickup: lastPickup, destination: lastDestination });
        }
      } catch (_) {}
      break;
    }
    case 'incoming_call':
      setStatus('Concorde is on the line', true);
      $('#concordeBanner').hidden = false;
      break;
    case 'call_ended':
      setStatus('Your driver is on the way', false);
      $('#concordeBanner').hidden = true;
      break;
    case 'demo_reset':
      bootState();
      setStatus('Your driver is on the way', false);
      $('#concordeBanner').hidden = true;
      break;
    default: break;
  }
}

bootState();
subscribe();
