export class SSEClient {
    constructor(onData) {
        this.es = null;
        this.onData = onData;
        this._connect();
    }

    _connect() {
        const statusEl = document.getElementById('sse-status') || this._createStatusEl();
        try {
            this.es = new EventSource('/events');
        } catch (err) {
            console.warn('SSE connection error', err);
            statusEl.textContent = 'SSE: error';
            setTimeout(()=> this._connect(), 5000);
            return;
        }
        this.es.onopen = function () {
            console.log('[SSE] Connection established - waiting for data');
            statusEl.textContent = 'SSE: connected';
        };

        this.es.onmessage = (function (e) {
            try {
                const d = JSON.parse(e.data);
                if (this.onData) this.onData(d);
            } catch (err) {
                console.debug('[SSE] Heartbeat');
            }
            statusEl.textContent = 'SSE: updated';
            setTimeout(function () { statusEl.textContent = 'SSE: connected'; }, 1000);
        }).bind(this);

        this.es.onerror = (function (err) {
            console.warn('[SSE] Error - attempting reconnection', err);
            statusEl.textContent = 'SSE: reconnecting...';
            try {
                this.es.close();
            } catch (e) { }
            const delay = Math.min(10000, 3000 + Math.random() * 7000);
            setTimeout(() => this._connect(), delay);
        }).bind(this);
    }

    _createStatusEl() {
        const statusEl = document.createElement('div');
        statusEl.id = 'sse-status';
        statusEl.style.cssText = 'position:fixed;right:8px;bottom:8px;padding:6px 10px;background:#222;color:#fff;border-radius:6px;font-size:12px;opacity:0.9';
        statusEl.textContent = 'SSE: connecting...';
        document.body.appendChild(statusEl);
        return statusEl;
    }
}
