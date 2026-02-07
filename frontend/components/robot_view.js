/**
 * Robot View — 2D top-down visualization of robot position and orientation.
 */

class RobotView {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.robot = {
            x: 0, y: 0,
            orientation: 0, // radians
            status: 'idle',
            trail: [],
        };
        this.gridSize = 40;
        this._resize();
        window.addEventListener('resize', () => this._resize());
        this._draw();
    }

    _resize() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height - 30;
    }

    updateState(robotState, action) {
        if (!robotState) return;

        // Simulate movement based on action
        const speed = 2;
        const rotSpeed = 0.08;

        switch (action) {
            case 'MOVE_FORWARD':
                this.robot.x += Math.cos(this.robot.orientation) * speed;
                this.robot.y += Math.sin(this.robot.orientation) * speed;
                break;
            case 'MOVE_BACKWARD':
                this.robot.x -= Math.cos(this.robot.orientation) * speed;
                this.robot.y -= Math.sin(this.robot.orientation) * speed;
                break;
            case 'ROTATE_LEFT':
                this.robot.orientation -= rotSpeed;
                break;
            case 'ROTATE_RIGHT':
                this.robot.orientation += rotSpeed;
                break;
        }

        this.robot.status = action || 'idle';

        // Keep trail
        this.robot.trail.push({ x: this.robot.x, y: this.robot.y });
        if (this.robot.trail.length > 200) {
            this.robot.trail.shift();
        }
    }

    _draw() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const cx = w / 2;
        const cy = h / 2;

        // Background
        ctx.fillStyle = '#0d1117';
        ctx.fillRect(0, 0, w, h);

        // Grid
        ctx.strokeStyle = '#1a2332';
        ctx.lineWidth = 0.5;
        const gs = this.gridSize;
        const offsetX = (cx + this.robot.x * 4) % gs;
        const offsetY = (cy + this.robot.y * 4) % gs;
        for (let x = offsetX; x < w; x += gs) {
            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
        }
        for (let y = offsetY; y < h; y += gs) {
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
        }

        // Trail
        if (this.robot.trail.length > 1) {
            ctx.strokeStyle = 'rgba(6, 182, 212, 0.2)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            for (let i = 0; i < this.robot.trail.length; i++) {
                const p = this.robot.trail[i];
                const sx = cx + (p.x - this.robot.x) * 4;
                const sy = cy + (p.y - this.robot.y) * 4;
                if (i === 0) ctx.moveTo(sx, sy);
                else ctx.lineTo(sx, sy);
            }
            ctx.stroke();
        }

        // Robot body
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(this.robot.orientation);

        // Body circle
        let bodyColor = '#3b82f6';
        if (this.robot.status === 'MOVE_FORWARD' || this.robot.status === 'MOVE_BACKWARD') {
            bodyColor = '#22c55e';
        } else if (this.robot.status.includes('ROTATE')) {
            bodyColor = '#06b6d4';
        } else if (this.robot.status === 'GRAB' || this.robot.status === 'RELEASE') {
            bodyColor = '#a855f7';
        } else if (this.robot.status === 'STOP' || this.robot.status === 'EMERGENCY_STOP') {
            bodyColor = '#ef4444';
        }

        // Glow
        ctx.shadowColor = bodyColor;
        ctx.shadowBlur = 20;

        // Body
        ctx.fillStyle = bodyColor;
        ctx.beginPath();
        ctx.arc(0, 0, 20, 0, Math.PI * 2);
        ctx.fill();

        ctx.shadowBlur = 0;

        // Direction arrow
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.moveTo(28, 0);
        ctx.lineTo(16, -8);
        ctx.lineTo(16, 8);
        ctx.closePath();
        ctx.fill();

        // Inner circle
        ctx.fillStyle = '#0d1117';
        ctx.beginPath();
        ctx.arc(0, 0, 8, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();

        // Status text
        ctx.fillStyle = '#64748b';
        ctx.font = '11px JetBrains Mono, monospace';
        ctx.fillText(`pos: (${this.robot.x.toFixed(1)}, ${this.robot.y.toFixed(1)})`, 10, h - 30);
        ctx.fillText(`rot: ${(this.robot.orientation * 180 / Math.PI).toFixed(1)}deg`, 10, h - 15);

        // Compass
        const compassR = 20;
        const compassX = w - 35;
        const compassY = 35;
        ctx.strokeStyle = '#2a3a4e';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(compassX, compassY, compassR, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = '#ef4444';
        ctx.beginPath();
        const nx = compassX + Math.cos(-this.robot.orientation + Math.PI / 2) * (compassR - 4);
        const ny = compassY - Math.sin(-this.robot.orientation + Math.PI / 2) * (compassR - 4);
        ctx.arc(nx, ny, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#64748b';
        ctx.font = '9px JetBrains Mono';
        ctx.fillText('N', compassX - 3, compassY - compassR - 4);

        requestAnimationFrame(() => this._draw());
    }
}
