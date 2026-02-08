/**
 * Robot View — 2D top-down factory map parsed from MuJoCo scene XML.
 * Fetches the raw XML from /scenes/factory_scene.xml and parses client-side.
 *
 * MuJoCo coordinate system: X-right, Y-forward (into screen), Z-up
 * Canvas: X-right, Y-down (so we flip Y)
 */

class RobotView {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');

        // Robot state (dead reckoning from commands)
        this.robot = {
            x: 0,      // meters, world X
            y: 0,      // meters, world Y
            angle: Math.PI / 2, // radians, facing +Y (forward into factory)
            trail: [],
        };

        // View settings
        this.viewRange = 8;     // meters visible from center
        this.followRobot = true;

        // Map data (loaded from XML)
        this.mapObjects = [];
        this.materials = {};
        this.floorSize = [8, 8];
        this.mapLoaded = false;
        this.mapError = null;

        // Category legend
        this.legendCategories = new Map();

        this._resize();
        window.addEventListener('resize', () => this._resize());
        this._loadMap();
        this._draw();
    }

    _resize() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = Math.max(100, rect.height - 30);
    }

    async _loadMap() {
        // Try fetching the scene XML and parsing client-side
        const xmlPaths = [
            '/scenes/factory_scene.xml',          // served by backend mount
            '../simulation/scenes/factory_scene.xml', // relative path fallback
        ];

        for (const path of xmlPaths) {
            try {
                const resp = await fetch(path);
                if (!resp.ok) continue;
                const xmlText = await resp.text();
                this._parseSceneXML(xmlText);
                if (this.mapObjects.length > 0) {
                    this.mapLoaded = true;
                    this.mapError = null;
                    console.log(`[RobotView] Map loaded from ${path}: ${this.mapObjects.length} objects`);
                    return;
                }
            } catch (e) {
                console.warn(`[RobotView] Failed to fetch ${path}:`, e.message);
            }
        }

        // Fallback: try /api/map (backend-parsed JSON)
        try {
            const resp = await fetch('/api/map');
            if (resp.ok) {
                const data = await resp.json();
                this.materials = data.materials || {};
                this.mapObjects = data.objects || [];
                this.floorSize = data.floor_size || [8, 8];
                this.mapLoaded = true;
                this._buildLegend();
                console.log(`[RobotView] Map loaded from /api/map: ${this.mapObjects.length} objects`);
                return;
            }
        } catch (e) {
            console.warn('[RobotView] /api/map also failed:', e.message);
        }

        this.mapError = 'Could not load map — retrying...';
        console.warn('[RobotView] All map sources failed, retrying in 3s');
        setTimeout(() => this._loadMap(), 3000);
    }

    // ========================
    // Client-side XML Parser
    // ========================

    _parseSceneXML(xmlText) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlText, 'text/xml');

        // Parse materials
        this.materials = {};
        for (const mat of doc.querySelectorAll('material')) {
            const name = mat.getAttribute('name');
            if (!name) continue;
            const rgbaStr = mat.getAttribute('rgba');
            let rgba = [0.5, 0.5, 0.5, 1.0];
            if (rgbaStr) {
                rgba = rgbaStr.split(/\s+/).map(Number);
            }
            this.materials[name] = {
                rgba: rgba,
                hex: this._rgbaToHex(rgba),
            };
        }

        // Parse geoms
        this.mapObjects = [];
        this.floorSize = [8, 8];

        for (const geom of doc.querySelectorAll('geom')) {
            const name = geom.getAttribute('name') || '';
            const type = geom.getAttribute('type') || 'sphere';
            const matName = geom.getAttribute('material') || '';

            // Position
            const posStr = geom.getAttribute('pos') || '0 0 0';
            const pos = posStr.split(/\s+/).map(Number);
            while (pos.length < 3) pos.push(0);

            // Size
            const sizeStr = geom.getAttribute('size') || '0.1';
            const size = sizeStr.split(/\s+/).map(Number);

            // Color from material
            const mat = this.materials[matName];
            const rgba = mat ? mat.rgba : [0.5, 0.5, 0.5, 1.0];
            const hex = mat ? mat.hex : '#808080';

            // Category
            const category = this._categorize(name, matName, type);

            // Floor — extract size, don't add as object
            if (type === 'plane') {
                if (size.length >= 2) this.floorSize = [size[0], size[1]];
                continue;
            }

            const obj = {
                name: name,
                type: type,
                category: category,
                material: matName,
                rgba: rgba,
                hex: hex,
                x: pos[0],
                y: pos[1],
                z: pos[2],
            };

            if (type === 'box') {
                obj.w = (size[0] || 0.1) * 2;
                obj.h = (size[1] || 0.1) * 2;
            } else if (type === 'cylinder') {
                obj.r = size[0] || 0.1;
            }

            this.mapObjects.push(obj);
        }

        // Sort by Z so ground-level draws first
        this.mapObjects.sort((a, b) => a.z - b.z);

        this._buildLegend();
    }

    _rgbaToHex(rgba) {
        const r = Math.round(Math.min(1, Math.max(0, rgba[0])) * 255);
        const g = Math.round(Math.min(1, Math.max(0, rgba[1])) * 255);
        const b = Math.round(Math.min(1, Math.max(0, rgba[2])) * 255);
        return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
    }

    _categorize(name, material, type) {
        const n = name.toLowerCase();
        const m = material.toLowerCase();

        if (n.includes('floor')) return 'floor';
        if (n.includes('wall')) return 'wall';
        if (n.includes('pillar')) return 'pillar';
        if (n.includes('lane')) return 'lane';

        // Shelf rack items (sA_, sB_ prefixes)
        if (n.startsWith('sa_') || n.startsWith('sb_')) {
            if (n.includes('upright') || n.includes('brace')) return 'shelf_frame';
            if (n.includes('shelf')) return 'shelf';
            if (n.includes('box')) return 'box';
        }

        // Conveyor items
        if (n.includes('conv')) {
            if (n.includes('belt')) return 'conveyor';
            if (n.includes('rail') || n.includes('leg')) return 'conveyor_frame';
            if (n.includes('box')) return 'box';
        }

        // Table items
        if (n.includes('table')) {
            if (n.includes('surface') || n.includes('top')) return 'table';
            if (n.includes('leg')) return 'table_leg';
            if (n.includes('box')) return 'box';
        }

        // Pallets
        if (n.includes('pallet') && !n.includes('box')) return 'pallet';
        if (n.startsWith('p1_') || n.startsWith('p2_')) return 'box';

        // Bollards
        if (n.includes('bollard')) return 'bollard';

        // Generic box detection
        if (n.includes('box') || m.includes('box')) return 'box';

        // Material-based fallback
        if (m.includes('shelf') || m.includes('beam')) return 'shelf_frame';
        if (m.includes('pallet')) return 'pallet';
        if (m.includes('safety') || m.includes('stripe')) return 'bollard';
        if (m.includes('conveyor')) return 'conveyor';
        if (m.includes('table')) return 'table';

        return 'other';
    }

    _buildLegend() {
        this.legendCategories.clear();
        for (const obj of this.mapObjects) {
            if (!this.legendCategories.has(obj.category)) {
                this.legendCategories.set(obj.category, obj.hex);
            }
        }
    }

    // ========================
    // State Update
    // ========================

    updateState(robotState, action) {
        if (!action || action === 'IDLE') return;

        const moveSpeed = 0.06;
        const rotSpeed = 0.06;

        switch (action) {
            case 'MOVE_FORWARD':
                this.robot.x += Math.cos(this.robot.angle) * moveSpeed;
                this.robot.y += Math.sin(this.robot.angle) * moveSpeed;
                break;
            case 'MOVE_BACKWARD':
                this.robot.x -= Math.cos(this.robot.angle) * moveSpeed;
                this.robot.y -= Math.sin(this.robot.angle) * moveSpeed;
                break;
            case 'ROTATE_LEFT':
                this.robot.angle += rotSpeed;
                break;
            case 'ROTATE_RIGHT':
                this.robot.angle -= rotSpeed;
                break;
        }

        const maxX = this.floorSize[0] - 0.5;
        const maxY = this.floorSize[1] - 0.5;
        this.robot.x = Math.max(-maxX, Math.min(maxX, this.robot.x));
        this.robot.y = Math.max(-maxY, Math.min(maxY, this.robot.y));

        this.robot.trail.push({ x: this.robot.x, y: this.robot.y });
        if (this.robot.trail.length > 500) this.robot.trail.shift();
    }

    // ========================
    // Rendering
    // ========================

    _worldToCanvas(wx, wy, scale, centerX, centerY) {
        if (this.followRobot) {
            return {
                x: centerX + (wx - this.robot.x) * scale,
                y: centerY - (wy - this.robot.y) * scale,
            };
        }
        return {
            x: centerX + wx * scale,
            y: centerY - wy * scale,
        };
    }

    _draw() {
        try {
            this._drawFrame();
        } catch (e) {
            console.error('[RobotView] Draw error:', e);
        }
        requestAnimationFrame(() => this._draw());
    }

    _drawFrame() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        if (w === 0 || h === 0) return;

        const cx = w / 2;
        const cy = h / 2;
        const scale = Math.min(w, h) / (this.viewRange * 2);
        const toC = (wx, wy) => this._worldToCanvas(wx, wy, scale, cx, cy);

        // Background
        ctx.fillStyle = '#1a1e24';
        ctx.fillRect(0, 0, w, h);

        // Grid (1m spacing)
        ctx.strokeStyle = '#222830';
        ctx.lineWidth = 0.5;
        const gridExtent = Math.max(this.floorSize[0], this.floorSize[1]);
        for (let gx = -gridExtent; gx <= gridExtent; gx++) {
            const p1 = toC(gx, -gridExtent);
            const p2 = toC(gx, gridExtent);
            ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
        }
        for (let gy = -gridExtent; gy <= gridExtent; gy++) {
            const p1 = toC(-gridExtent, gy);
            const p2 = toC(gridExtent, gy);
            ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
        }

        // Map objects
        if (this.mapLoaded) {
            for (const obj of this.mapObjects) {
                this._drawObject(ctx, obj, scale, toC);
            }
        }

        // Robot trail
        if (this.robot.trail.length > 1) {
            ctx.strokeStyle = 'rgba(6, 182, 212, 0.15)';
            ctx.lineWidth = Math.max(2, scale * 0.05);
            ctx.beginPath();
            for (let i = 0; i < this.robot.trail.length; i++) {
                const p = toC(this.robot.trail[i].x, this.robot.trail[i].y);
                if (i === 0) ctx.moveTo(p.x, p.y);
                else ctx.lineTo(p.x, p.y);
            }
            ctx.stroke();
        }

        // Robot
        this._drawRobot(ctx, scale, toC);

        // HUD
        this._drawHUD(ctx, w, h, scale);

        // Legend
        if (this.mapLoaded) {
            this._drawLegend(ctx, w, h);
        }
    }

    _drawObject(ctx, obj, scale, toC) {
        const cat = obj.category;
        const color = obj.hex;

        if (cat === 'lane') {
            this._drawLane(ctx, obj, scale, toC);
            return;
        }

        if (obj.type === 'box') {
            const objW = obj.w || 0.2;
            const objH = obj.h || 0.2;
            const wPx = objW * scale;
            const hPx = objH * scale;
            const p = toC(obj.x - objW / 2, obj.y + objH / 2);

            if (cat === 'wall') {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
                this._drawLabel(ctx, toC(obj.x, obj.y), obj.name, '#999', scale);
            } else if (cat === 'pillar') {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
                ctx.strokeStyle = '#777';
                ctx.lineWidth = 1;
                ctx.strokeRect(p.x, p.y, wPx, hPx);
            } else if (cat === 'shelf' || cat === 'shelf_frame') {
                if (cat === 'shelf') {
                    ctx.fillStyle = 'rgba(0,0,0,0.3)';
                    ctx.fillRect(p.x + 2, p.y + 2, wPx, hPx);
                }
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
                ctx.strokeStyle = this._lighten(color, 0.3);
                ctx.lineWidth = 1;
                ctx.strokeRect(p.x, p.y, wPx, hPx);
                if (cat === 'shelf') {
                    this._drawLabel(ctx, toC(obj.x, obj.y), obj.name, '#8ab4f8', scale);
                }
            } else if (cat === 'conveyor') {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
                ctx.strokeStyle = this._lighten(color, 0.15);
                ctx.lineWidth = 1;
                const rollerCount = Math.max(3, Math.floor(wPx / 12));
                for (let i = 1; i < rollerCount; i++) {
                    const rx = p.x + (wPx * i / rollerCount);
                    ctx.beginPath(); ctx.moveTo(rx, p.y); ctx.lineTo(rx, p.y + hPx); ctx.stroke();
                }
                this._drawLabel(ctx, toC(obj.x, obj.y), 'CONVEYOR', '#888', scale);
            } else if (cat === 'conveyor_frame') {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
            } else if (cat === 'table') {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
                ctx.strokeStyle = '#777';
                ctx.lineWidth = 1;
                ctx.strokeRect(p.x, p.y, wPx, hPx);
                this._drawLabel(ctx, toC(obj.x, obj.y), 'TABLE', '#888', scale);
            } else if (cat === 'table_leg') {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
            } else if (cat === 'pallet') {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
                ctx.strokeStyle = this._darken(color, 0.2);
                ctx.lineWidth = 1;
                for (let i = 1; i < 4; i++) {
                    const sy = p.y + (hPx * i / 4);
                    ctx.beginPath(); ctx.moveTo(p.x, sy); ctx.lineTo(p.x + wPx, sy); ctx.stroke();
                }
                this._drawLabel(ctx, toC(obj.x, obj.y), obj.name, '#ccc', scale);
            } else if (cat === 'box') {
                const cp = toC(obj.x, obj.y);
                const r = Math.max(2, scale * 0.08);
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(cp.x, cp.y, r, 0, Math.PI * 2);
                ctx.fill();
            } else {
                ctx.fillStyle = color;
                ctx.fillRect(p.x, p.y, wPx, hPx);
            }
        } else if (obj.type === 'cylinder') {
            const cp = toC(obj.x, obj.y);
            const r = obj.r || 0.1;

            if (cat === 'bollard') {
                const rPx = Math.max(3, r * scale * 3);
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(cp.x, cp.y, rPx, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#222';
                ctx.beginPath();
                ctx.arc(cp.x, cp.y, rPx * 0.5, 0, Math.PI * 2);
                ctx.fill();
            } else {
                const rPx = Math.max(2, r * scale);
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(cp.x, cp.y, rPx, 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    _drawLane(ctx, obj, scale, toC) {
        const halfW = (obj.w || 0.1) / 2;
        const halfH = (obj.h || 0.1) / 2;
        const isVertical = halfH > halfW;

        const r = Math.round(obj.rgba[0] * 255);
        const g = Math.round(obj.rgba[1] * 255);
        const b = Math.round(obj.rgba[2] * 255);
        ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, 0.35)`;
        ctx.lineWidth = 3;
        ctx.setLineDash([scale * 0.3, scale * 0.2]);

        if (isVertical) {
            const p1 = toC(obj.x, obj.y - halfH);
            const p2 = toC(obj.x, obj.y + halfH);
            ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
        } else {
            const p1 = toC(obj.x - halfW, obj.y);
            const p2 = toC(obj.x + halfW, obj.y);
            ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
        }
        ctx.setLineDash([]);
    }

    _drawLabel(ctx, pos, text, color, scale) {
        ctx.fillStyle = color;
        ctx.font = `${Math.max(7, scale * 0.18)}px JetBrains Mono, monospace`;
        ctx.textAlign = 'center';
        const display = text.replace(/^s[AB]_/, '').replace(/^conv_/, '').replace(/_/g, ' ').toUpperCase();
        ctx.fillText(display, pos.x, pos.y + 4);
    }

    _drawRobot(ctx, scale, toC) {
        const rp = toC(this.robot.x, this.robot.y);
        const robotR = Math.max(8, scale * 0.25);

        ctx.save();
        ctx.shadowColor = '#3b82f6';
        ctx.shadowBlur = 15;
        ctx.fillStyle = 'rgba(59, 130, 246, 0.3)';
        ctx.beginPath();
        ctx.arc(rp.x, rp.y, robotR * 1.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

        ctx.fillStyle = '#3b82f6';
        ctx.beginPath();
        ctx.arc(rp.x, rp.y, robotR, 0, Math.PI * 2);
        ctx.fill();

        // Direction arrow
        const arrowLen = robotR * 1.6;
        const ax = rp.x + Math.cos(this.robot.angle) * arrowLen;
        const ay = rp.y - Math.sin(this.robot.angle) * arrowLen;
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        const perpX = -Math.sin(this.robot.angle);
        const perpY = -Math.cos(this.robot.angle);
        const backX = rp.x + Math.cos(this.robot.angle) * robotR * 0.7;
        const backY = rp.y - Math.sin(this.robot.angle) * robotR * 0.7;
        ctx.lineTo(backX + perpX * robotR * 0.5, backY + perpY * robotR * 0.5);
        ctx.lineTo(backX - perpX * robotR * 0.5, backY - perpY * robotR * 0.5);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = '#1a1e24';
        ctx.beginPath();
        ctx.arc(rp.x, rp.y, robotR * 0.3, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
    }

    _drawHUD(ctx, w, h, scale) {
        const textColor = '#64748b';

        ctx.fillStyle = textColor;
        ctx.font = '10px JetBrains Mono, monospace';
        ctx.textAlign = 'left';
        ctx.fillText(`pos: (${this.robot.x.toFixed(2)}, ${this.robot.y.toFixed(2)})`, 8, h - 24);
        ctx.fillText(`hdg: ${(this.robot.angle * 180 / Math.PI).toFixed(0)}deg`, 8, h - 10);

        // Scale bar
        ctx.textAlign = 'right';
        ctx.fillText('1m', w - 8, h - 24);
        const barLen = scale;
        ctx.strokeStyle = textColor;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(w - 8 - barLen, h - 18);
        ctx.lineTo(w - 8, h - 18);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(w - 8 - barLen, h - 22);
        ctx.lineTo(w - 8 - barLen, h - 14);
        ctx.moveTo(w - 8, h - 22);
        ctx.lineTo(w - 8, h - 14);
        ctx.stroke();

        // Compass
        const compassR = 16;
        const compX = w - 28;
        const compY = 28;
        ctx.strokeStyle = '#2a3a4e';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(compX, compY, compassR, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = '#ef4444';
        ctx.beginPath();
        ctx.arc(compX, compY - compassR + 4, 3, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = textColor;
        ctx.font = '8px JetBrains Mono';
        ctx.textAlign = 'center';
        ctx.fillText('N', compX, compY - compassR - 4);
        const hdgX = compX + Math.cos(this.robot.angle) * (compassR - 5);
        const hdgY = compY - Math.sin(this.robot.angle) * (compassR - 5);
        ctx.fillStyle = '#3b82f6';
        ctx.beginPath();
        ctx.arc(hdgX, hdgY, 2.5, 0, Math.PI * 2);
        ctx.fill();

        // Map status label
        ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
        ctx.font = '9px JetBrains Mono, monospace';
        ctx.textAlign = 'left';
        if (this.mapLoaded) {
            ctx.fillText(`FACTORY FLOOR — ${this.mapObjects.length} objects from scene XML`, 8, 14);
        } else if (this.mapError) {
            ctx.fillStyle = 'rgba(239, 68, 68, 0.6)';
            ctx.fillText(this.mapError, 8, 14);
        } else {
            ctx.fillText('LOADING MAP...', 8, 14);
        }
    }

    _drawLegend(ctx, w, h) {
        const legendX = 8;
        let legendY = 26;
        const dotR = 4;
        const lineH = 14;

        ctx.font = '8px JetBrains Mono, monospace';
        ctx.textAlign = 'left';

        const friendlyNames = {
            wall: 'Wall',
            pillar: 'Pillar',
            shelf: 'Shelf',
            shelf_frame: 'Shelf Frame',
            conveyor: 'Conveyor Belt',
            conveyor_frame: 'Conv. Frame',
            table: 'Work Table',
            table_leg: 'Table Leg',
            pallet: 'Pallet',
            bollard: 'Safety Bollard',
            box: 'Box / Cargo',
            lane: 'Lane Marking',
            other: 'Other',
        };

        const majorCategories = ['wall', 'pillar', 'shelf', 'conveyor', 'table', 'pallet', 'bollard', 'box', 'lane'];

        for (const cat of majorCategories) {
            if (!this.legendCategories.has(cat)) continue;
            const color = this.legendCategories.get(cat);
            const label = friendlyNames[cat] || cat;

            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(legendX + dotR, legendY + dotR, dotR, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = '#94a3b8';
            ctx.fillText(label, legendX + dotR * 2 + 6, legendY + dotR + 3);

            legendY += lineH;
        }
    }

    // --- Color utilities ---

    _lighten(hex, amount) {
        const rgb = this._hexToRgb(hex);
        return `rgb(${Math.min(255, rgb.r + amount * 255)}, ${Math.min(255, rgb.g + amount * 255)}, ${Math.min(255, rgb.b + amount * 255)})`;
    }

    _darken(hex, amount) {
        const rgb = this._hexToRgb(hex);
        return `rgb(${Math.max(0, rgb.r - amount * 255)}, ${Math.max(0, rgb.g - amount * 255)}, ${Math.max(0, rgb.b - amount * 255)})`;
    }

    _hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16),
        } : { r: 128, g: 128, b: 128 };
    }
}
