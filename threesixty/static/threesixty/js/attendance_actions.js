// Check-in / check-out shared by the Dashboard banner and the Attendance page (reference: attCheckIn / attCheckOut).
// Everyone's location is recorded (REQ-ATT-04) — the API refuses a check-in without one.
import { api } from './api.js';
import { customAlert, apiErrorMessage } from './ui.js';

export function getLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) { reject(new Error('This device/browser cannot share location.')); return; }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6), accuracy_m: Math.round(p.coords.accuracy || 0) }),
      (err) => reject(new Error(err && err.code === 1
        ? 'Location permission was denied. Allow location for this page in your browser settings, then try again.'
        : 'Could not get your location. Switch on GPS / location services and try again.')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  });
}

async function mark(kind) {
  let loc;
  try { loc = await getLocation(); }
  catch (e) { await customAlert(`${kind === 'check-in' ? 'Check-in' : 'Check-out'} needs your location. ${e.message}`); return false; }
  try { await api.post(`attendance/${kind}/`, loc); return true; }
  catch (e) { await customAlert(apiErrorMessage(e)); return false; }
}
export const checkIn = () => mark('check-in');
export const checkOut = () => mark('check-out');

// "9:30 AM" from "09:30"; "7h 05m" from minutes — same formats as the reference.
export function fmtTime(hm) {
  if (!hm) return '—';
  const [h, m] = hm.split(':').map(Number);
  return `${(h % 12) || 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}
export function fmtDur(mins) {
  if (mins === null || mins === undefined || mins < 0) return '—';
  return `${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, '0')}m`;
}
