export function escHtml(s) {
	if (s === undefined || s === null) return '';
	const str = String(s);
	return str
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;')
		.replace(/'/g, '&#39;');
}

export function normalizeColor(c) {
	if (!c) return '#888';
	let s = String(c);
	if (!s.startsWith('#')) s = '#' + s;
	// expand short hex (#abc -> #aabbcc)
	if (s.length === 4) {
		s = '#' + s[1] + s[1] + s[2] + s[2] + s[3] + s[3];
	}
	return s;
}

export function getContrastColor(hex) {
	if (!hex) return '#000';
	let s = String(hex).replace(/^#/, '');
	if (s.length === 3) {
		s = s.split('').map(c => c + c).join('');
	}
	const r = parseInt(s.substr(0, 2), 16) || 0;
	const g = parseInt(s.substr(2, 2), 16) || 0;
	const b = parseInt(s.substr(4, 2), 16) || 0;
	const yiq = (r * 299 + g * 587 + b * 114) / 1000;
	return yiq >= 128 ? '#000' : '#fff';
}

export function fuzzyMatch(needle, hay) {
	if (!needle) return true;
	const n = String(needle).toLowerCase();
	const h = String(hay || '').toLowerCase();
	let p = 0;
	for (let ch of h) {
		if (ch === n[p]) p++;
		if (p === n.length) return true;
	}
	return false;
}

export function formatTime(ts) {
	if (!ts) return '';
	const d = new Date(ts * 1000);
	return d.toLocaleTimeString();
}

export function showAlert(msg, timeout = 3000) {
	const alertDiv = document.getElementById('alert');
	if (!alertDiv) return;
	alertDiv.textContent = msg;
	alertDiv.style.display = 'block';
	setTimeout(() => { alertDiv.style.display = 'none'; }, timeout);
}

// parse CSV handling quoted fields (handles commas inside quoted fields)
export function parseCSV(text) {
	const lines = text.split('\n').map(l => l.trim()).filter(l => l.length > 0);
	if (lines.length < 2) return [];
	const splitLine = (ln) => {
		return ln.split(/,(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)/).map(f => f.replace(/^\"|\"$/g, '').trim()); // ???
	};
	const headers = splitLine(lines[0]);
	const rows = lines.slice(1).map(line => {
		const parts = splitLine(line);
		const obj = {};
		headers.forEach((h, i) => { obj[h] = parts[i] ? parts[i].trim() : ''; });
		return obj;
	});
	return rows;
}