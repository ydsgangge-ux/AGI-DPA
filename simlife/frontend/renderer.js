/**
 * SimLife Canvas 渲染器 v2
 * 640x360 画布，精细卡通风格
 */

const TILE = 16;
const W = 640;
const H = 360;

class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.scene = null;
    this.mainChar = null;
    this.npcs = [];
    this.bgNpcs = [];
    this.time = 0;
    this.weather = 'cloudy';
    this.particles = [];
    this.fadeAlpha = 0;
    this.fading = false;
    this.fadeDir = 0;
    this.onFadeComplete = null;
  }

  clear(color = '#1a1a2e') {
    this.ctx.fillStyle = color;
    this.ctx.fillRect(0, 0, W, H);
  }

  fillCircle(cx, cy, r, color) {
    this.ctx.fillStyle = color;
    this.ctx.beginPath();
    this.ctx.arc(cx, cy, r, 0, Math.PI * 2);
    this.ctx.fill();
  }

  roundRect(x, y, w, h, r, color) {
    this.ctx.fillStyle = color;
    this.ctx.beginPath();
    this.ctx.roundRect(x, y, w, h, r);
    this.ctx.fill();
  }

  // ── 角色绘制（精细卡通风）────────────────────

  drawChar(x, y, config) {
    /**
     * config: { hairColor, outfitColor, skinColor, action, facing }
     * action: 'stand' | 'walk' | 'sit' | 'sleep' | 'phone' | 'work'
     */
    const c = this.ctx;
    const skin = config.skinColor || '#f5d0a9';
    const hair = config.hairColor || '#4A3728';
    const outfit = config.outfitColor || '#F5F0E8';
    const px = Math.floor(x);
    const py = Math.floor(y);

    c.save();

    if (config.action === 'sleep') {
      this._drawSleeping(px, py, skin, hair, outfit);
      c.restore();
      return;
    }

    if (config.action === 'sit') {
      this._drawSitting(px, py, skin, hair, outfit);
      c.restore();
      return;
    }

    const bob = config.action === 'walk' ? Math.sin(this.time * 0.15) * 2 : 0;
    const legOff = config.action === 'walk' ? Math.sin(this.time * 0.3) * 3 : 0;
    const breathe = Math.sin(this.time * 0.04) * 0.8;

    // 阴影
    c.fillStyle = 'rgba(0,0,0,0.15)';
    c.beginPath();
    c.ellipse(px + 16, py + 50, 14, 4, 0, 0, Math.PI * 2);
    c.fill();

    // 腿
    c.fillStyle = '#3a3a5a';
    this._roundRect(c, px + 8, py + 38 + bob + legOff, 6, 12, 2);
    this._roundRect(c, px + 18, py + 38 + bob - legOff, 6, 12, 2);
    // 鞋子
    c.fillStyle = '#555';
    this._roundRect(c, px + 6, py + 48 + bob + legOff, 8, 4, 2);
    this._roundRect(c, px + 18, py + 48 + bob - legOff, 8, 4, 2);

    // 身体
    c.fillStyle = outfit;
    this._roundRect(c, px + 4, py + 20 + bob + breathe, 24, 20, 4);
    // 领口
    c.fillStyle = skin;
    this._roundRect(c, px + 12, py + 19 + bob + breathe, 8, 5, 2);

    // 手臂
    c.fillStyle = skin;
    if (config.action === 'phone') {
      // 举手看手机
      c.save();
      c.translate(px + 30, py + 22 + bob);
      c.rotate(-0.3);
      this._roundRect(c, 0, 0, 6, 16, 3);
      // 手机
      c.fillStyle = '#333';
      this._roundRect(c, -1, -8, 10, 14, 2);
      c.fillStyle = '#4a8af5';
      this._roundRect(c, 0, -7, 8, 11, 1);
      c.restore();
      // 另一只手
      c.fillStyle = skin;
      this._roundRect(c, px - 2, py + 22 + bob, 6, 14, 3);
    } else if (config.action === 'work') {
      // 手放桌上位置
      this._roundRect(c, px + 1, py + 28 + bob, 6, 10, 3);
      this._roundRect(c, px + 25, py + 28 + bob, 6, 10, 3);
    } else {
      const armSwing = config.action === 'walk' ? Math.sin(this.time * 0.3) * 4 : 0;
      this._roundRect(c, px - 1, py + 22 + bob + armSwing, 6, 14, 3);
      this._roundRect(c, px + 27, py + 22 + bob - armSwing, 6, 14, 3);
    }

    // 头
    c.fillStyle = skin;
    c.beginPath();
    c.arc(px + 16, py + 10 + bob, 12, 0, Math.PI * 2);
    c.fill();

    // 头发
    c.fillStyle = hair;
    c.beginPath();
    c.arc(px + 16, py + 6 + bob, 13, Math.PI, Math.PI * 2);
    c.fill();
    c.fillRect(px + 3, py + 2 + bob, 26, 8);
    // 刘海
    c.beginPath();
    c.arc(px + 12, py + 8 + bob, 6, 0.2, Math.PI + 0.2);
    c.fill();

    // 腮红
    c.fillStyle = 'rgba(255,150,150,0.25)';
    c.beginPath(); c.arc(px + 6, py + 13 + bob, 3, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(px + 26, py + 13 + bob, 3, 0, Math.PI * 2); c.fill();

    // 眼睛
    c.fillStyle = '#333';
    c.beginPath(); c.ellipse(px + 10, py + 10 + bob, 2.2, 2.8, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.ellipse(px + 22, py + 10 + bob, 2.2, 2.8, 0, 0, Math.PI * 2); c.fill();
    // 眼睛高光
    c.fillStyle = '#fff';
    c.beginPath(); c.arc(px + 11, py + 9 + bob, 1, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(px + 23, py + 9 + bob, 1, 0, Math.PI * 2); c.fill();

    // 嘴
    c.strokeStyle = '#c47a6a';
    c.lineWidth = 1.5;
    c.lineCap = 'round';
    c.beginPath();
    c.arc(px + 16, py + 14 + bob, 3, 0.15 * Math.PI, 0.85 * Math.PI);
    c.stroke();

    c.restore();
  }

  _drawSleeping(px, py, skin, hair, outfit) {
    const c = this.ctx;
    // 被子
    c.fillStyle = '#c0b8d0';
    this._roundRect(c, px - 5, py + 16, 50, 22, 6);
    c.fillStyle = '#a8a0b8';
    this._roundRect(c, px - 3, py + 14, 46, 8, 4);
    // 枕头
    c.fillStyle = '#f0e8d8';
    this._roundRect(c, px + 26, py + 10, 20, 14, 6);
    // 头
    c.fillStyle = skin;
    c.beginPath(); c.arc(px + 36, py + 14, 9, 0, Math.PI * 2); c.fill();
    // 头发
    c.fillStyle = hair;
    c.beginPath();
    c.arc(px + 36, py + 10, 10, Math.PI, Math.PI * 2);
    c.fill();
    c.fillRect(px + 27, py + 6, 18, 6);
    // 闭眼
    c.strokeStyle = '#333';
    c.lineWidth = 1.5;
    c.beginPath(); c.moveTo(px + 32, py + 14); c.lineTo(px + 36, py + 13); c.stroke();
    c.beginPath(); c.moveTo(px + 38, py + 13); c.lineTo(px + 42, py + 14); c.stroke();
    // Zzz
    const zOff = Math.sin(this.time * 0.05) * 2;
    c.fillStyle = 'rgba(200,200,255,0.6)';
    c.font = '10px sans-serif';
    c.fillText('z', px + 46, py + 6 + zOff);
    c.font = '13px sans-serif';
    c.fillText('z', px + 54, py - 2 + zOff * 1.3);
    c.font = '16px sans-serif';
    c.fillText('Z', px + 62, py - 10 + zOff * 1.6);
  }

  _drawSitting(px, py, skin, hair, outfit) {
    const c = this.ctx;
    const breathe = Math.sin(this.time * 0.04) * 0.5;

    // 阴影
    c.fillStyle = 'rgba(0,0,0,0.12)';
    c.beginPath(); c.ellipse(px + 16, py + 50, 14, 4, 0, 0, Math.PI * 2); c.fill();

    // 腿（弯曲）
    c.fillStyle = '#3a3a5a';
    this._roundRect(c, px + 6, py + 38, 8, 10, 2);
    this._roundRect(c, px + 18, py + 38, 8, 10, 2);
    c.fillStyle = '#555';
    this._roundRect(c, px + 4, py + 46, 12, 4, 2);
    this._roundRect(c, px + 16, py + 46, 12, 4, 2);

    // 身体
    c.fillStyle = outfit;
    this._roundRect(c, px + 4, py + 20 + breathe, 24, 18, 4);

    // 手臂
    c.fillStyle = skin;
    this._roundRect(c, px - 1, py + 22 + breathe, 6, 12, 3);
    this._roundRect(c, px + 27, py + 22 + breathe, 6, 12, 3);

    // 头
    c.fillStyle = skin;
    c.beginPath(); c.arc(px + 16, py + 10, 12, 0, Math.PI * 2); c.fill();
    // 头发
    c.fillStyle = hair;
    c.beginPath();
    c.arc(px + 16, py + 6, 13, Math.PI, Math.PI * 2);
    c.fill();
    c.fillRect(px + 3, py + 2, 26, 8);

    // 眼睛
    c.fillStyle = '#333';
    c.beginPath(); c.ellipse(px + 10, py + 10, 2.2, 2.8, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.ellipse(px + 22, py + 10, 2.2, 2.8, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#fff';
    c.beginPath(); c.arc(px + 11, py + 9, 1, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(px + 23, py + 9, 1, 0, Math.PI * 2); c.fill();

    // 腮红
    c.fillStyle = 'rgba(255,150,150,0.25)';
    c.beginPath(); c.arc(px + 6, py + 13, 3, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(px + 26, py + 13, 3, 0, Math.PI * 2); c.fill();

    // 微笑
    c.strokeStyle = '#c47a6a'; c.lineWidth = 1.5; c.lineCap = 'round';
    c.beginPath(); c.arc(px + 16, py + 14, 3, 0.15 * Math.PI, 0.85 * Math.PI); c.stroke();
  }

  drawNpc(x, y, variant, frame) {
    const npcColors = [
      { hair: '#2a2a2a', outfit: '#e74c3c', skin: '#f5d0a9' },
      { hair: '#8B4513', outfit: '#3498db', skin: '#deb887' },
      { hair: '#1a1a1a', outfit: '#2ecc71', skin: '#f0c8a0' },
      { hair: '#654321', outfit: '#9b59b6', skin: '#f5d0a9' },
      { hair: '#4a4a4a', outfit: '#e67e22', skin: '#deb887' },
      { hair: '#2c2c2c', outfit: '#1abc9c', skin: '#f0c8a0' },
      { hair: '#5a3a1a', outfit: '#f39c12', skin: '#f5d0a9' },
      { hair: '#333', outfit: '#c0392b', skin: '#deb887' },
      { hair: '#6a4a2a', outfit: '#2980b9', skin: '#f0c8a0' },
      { hair: '#1c1c1c', outfit: '#27ae60', skin: '#f5d0a9' },
    ];
    const idx = (variant || 0) % npcColors.length;
    const col = npcColors[idx];
    this.drawChar(x, y, {
      hairColor: col.hair,
      outfitColor: col.outfit,
      skinColor: col.skin,
      action: 'stand',
    });
  }

  // ── 场景绘制 ────────────────────────────────

  drawScene(scene, mainChar, activeNpcs, bgNpcCount) {
    this.scene = scene;
    this.mainChar = mainChar;
    this.time++;

    this.clear(this._getSkyColor());

    const drawFn = SCENE_RENDERERS[scene];
    if (drawFn) {
      drawFn(this);
    } else {
      this._drawDefaultScene();
    }

    // 活跃 NPC
    if (activeNpcs && activeNpcs.length > 0) {
      const npcPositions = this._getNpcPositions(scene);
      activeNpcs.forEach((npc, i) => {
        const pos = npcPositions[i] || { x: 400, y: 170 };
        this.drawNpc(pos.x, pos.y, npc.variant || i);
      });
    }

    // 主角（最后画，在最上层）
    if (mainChar) {
      const pos = this._getMainCharPos(scene);
      const action = this._getMainCharAction(scene);
      this.drawChar(pos.x, pos.y, {
        hairColor: mainChar.hairColor,
        outfitColor: mainChar.outfitColor,
        action: action,
      });
    }

    // 背景 NPC
    if (bgNpcCount > 0) {
      for (let i = 0; i < bgNpcCount; i++) {
        const bx = ((this.time * 0.3 + i * 160) % (W + 80)) - 40;
        const by = 220 + (i % 3) * 16;
        this.drawNpc(bx, by, i + 3);
      }
    }

    // 淡入淡出
    if (this.fading) {
      this.fadeAlpha += this.fadeDir * 0.04;
      if (this.fadeAlpha >= 1) { this.fadeAlpha = 1; if (this.onFadeComplete) this.onFadeComplete(); }
      if (this.fadeAlpha <= 0) { this.fadeAlpha = 0; this.fading = false; }
      this.ctx.fillStyle = `rgba(0,0,0,${this.fadeAlpha})`;
      this.ctx.fillRect(0, 0, W, H);
    }

    // 天气粒子
    this._drawWeather();
  }

  startFade(callback) {
    this.fading = true;
    this.fadeDir = 1;
    this.fadeAlpha = 0;
    this.onFadeComplete = () => { if (callback) callback(); this.fadeDir = -1; };
  }

  setWeather(w) { this.weather = w; this.particles = []; }

  _roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
    ctx.fill();
  }

  _getSkyColor() {
    const skyMap = {
      'HOME_SLEEPING': '#0a0a20',
      'HOME_MORNING': '#1a1520',
      'HOME_EVENING': '#1a1a2e',
      'HOME_WEEKEND_LAZY': '#1a1520',
      'COMMUTE_TO_WORK': '#3a4a5a',
      'COMMUTE_TO_HOME': '#2a3a4a',
      'OFFICE_WORKING': '#f5f5f0',
      'OFFICE_MEETING': '#f5f5f0',
      'OFFICE_LUNCH': '#e8e8e0',
      'CAFE': '#f0e8d8',
      'PARK': '#87CEEB',
      'SUPERMARKET': '#f0f0e8',
      'STREET_WANDERING': '#87CEEB',
      'FRIEND_HANGOUT': '#f0e8d8',
      'OVERTIME': '#0a0a20',
    };
    return skyMap[this.scene] || '#1a1a2e';
  }

  _getMainCharPos(scene) {
    const posMap = {
      'HOME_SLEEPING': { x: 120, y: 130 },
      'HOME_MORNING': { x: 360, y: 160 },
      'HOME_EVENING': { x: 280, y: 170 },
      'HOME_WEEKEND_LAZY': { x: 120, y: 135 },
      'COMMUTE_TO_WORK': { x: 300, y: 200 },
      'COMMUTE_TO_HOME': { x: 300, y: 200 },
      'OFFICE_WORKING': { x: 240, y: 170 },
      'OFFICE_MEETING': { x: 360, y: 170 },
      'OFFICE_LUNCH': { x: 400, y: 200 },
      'CAFE': { x: 320, y: 180 },
      'PARK': { x: 300, y: 210 },
      'SUPERMARKET': { x: 320, y: 210 },
      'STREET_WANDERING': { x: 300, y: 210 },
      'FRIEND_HANGOUT': { x: 280, y: 190 },
      'OVERTIME': { x: 240, y: 170 },
    };
    return posMap[scene] || { x: 300, y: 180 };
  }

  _getMainCharAction(scene) {
    const actionMap = {
      'HOME_SLEEPING': 'sleep',
      'HOME_MORNING': 'stand',
      'HOME_EVENING': 'sit',
      'HOME_WEEKEND_LAZY': 'sleep',
      'COMMUTE_TO_WORK': 'walk',
      'COMMUTE_TO_HOME': 'walk',
      'OFFICE_WORKING': 'work',
      'OFFICE_MEETING': 'stand',
      'OFFICE_LUNCH': 'walk',
      'CAFE': 'sit',
      'PARK': 'walk',
      'SUPERMARKET': 'walk',
      'STREET_WANDERING': 'walk',
      'FRIEND_HANGOUT': 'sit',
      'OVERTIME': 'work',
    };
    return actionMap[scene] || 'stand';
  }

  _getNpcPositions(scene) {
    const npcPosMap = {
      'OFFICE_WORKING': [{ x: 320, y: 170 }, { x: 400, y: 170 }],
      'OFFICE_LUNCH': [{ x: 440, y: 200 }],
      'CAFE': [{ x: 280, y: 180 }],
      'FRIEND_HANGOUT': [{ x: 360, y: 190 }],
    };
    return npcPosMap[scene] || [];
  }

  _drawWeather() {
    const c = this.ctx;
    // 粒子初始化
    if (this.weather === 'rainy' || this.weather === 'heavy_rain') {
      const target = this.weather === 'heavy_rain' ? 120 : 60;
      while (this.particles.length < target) {
        this.particles.push({ x: Math.random() * W, y: Math.random() * H, speed: 4 + Math.random() * 6 });
      }
      c.strokeStyle = 'rgba(180,200,255,0.4)';
      c.lineWidth = 1;
      for (const p of this.particles) {
        c.beginPath(); c.moveTo(p.x, p.y); c.lineTo(p.x - 1, p.y + p.speed * 2); c.stroke();
        p.y += p.speed;
        p.x -= 0.5;
        if (p.y > H) { p.y = -10; p.x = Math.random() * W; }
      }
    } else if (this.weather === 'snow') {
      while (this.particles.length < 50) {
        this.particles.push({ x: Math.random() * W, y: Math.random() * H, r: 1.5 + Math.random() * 2, speed: 0.5 + Math.random() * 1.5, drift: Math.random() * 2 - 1 });
      }
      c.fillStyle = 'rgba(255,255,255,0.7)';
      for (const p of this.particles) {
        c.beginPath(); c.arc(p.x, p.y, p.r, 0, Math.PI * 2); c.fill();
        p.y += p.speed;
        p.x += Math.sin(this.time * 0.02 + p.drift) * 0.5;
        if (p.y > H) { p.y = -5; p.x = Math.random() * W; }
      }
    } else {
      // 非天气场景，清除粒子
      if (this.particles.length > 0) this.particles = [];
    }
  }

  _drawDefaultScene() {
    this.roundRect(0, 260, W, 100, 0, '#2a2a3a');
  }
}

// ── 场景渲染函数（精细版）────────────────────

const SCENE_RENDERERS = {

  HOME_SLEEPING(r) {
    const c = r.ctx;
    // 墙壁渐变
    const wg = c.createLinearGradient(0, 0, 0, 220);
    wg.addColorStop(0, '#1a1a30'); wg.addColorStop(1, '#0f0f22');
    c.fillStyle = wg; c.fillRect(0, 0, W, 220);

    // 地板
    const fg = c.createLinearGradient(0, 220, 0, H);
    fg.addColorStop(0, '#3a3228'); fg.addColorStop(1, '#2a2218');
    c.fillStyle = fg; c.fillRect(0, 220, W, H - 220);

    // 墙线
    c.strokeStyle = 'rgba(255,255,255,0.03)'; c.lineWidth = 1;
    for (let i = 0; i < 6; i++) { c.beginPath(); c.moveTo(0, 220); c.lineTo(W, 220 - i * 40); c.stroke(); }

    // 窗户
    r.roundRect(60, 60, 80, 60, 3, '#1a2a4a');
    r.roundRect(63, 63, 36, 26, 1, '#2a3a5a');
    r.roundRect(102, 63, 36, 26, 1, '#2a3a5a');
    // 窗框
    c.fillStyle = '#555';
    c.fillRect(98, 60, 4, 60);
    c.fillRect(60, 90, 80, 3);
    // 月光
    c.fillStyle = 'rgba(232,232,208,0.6)';
    c.beginPath(); c.arc(110, 75, 8, 0, Math.PI * 2); c.fill();
    c.fillStyle = 'rgba(232,232,208,0.08)';
    c.fillRect(63, 63, 75, 54);

    // 月光投射到地面
    c.fillStyle = 'rgba(200,200,180,0.04)';
    c.beginPath();
    c.moveTo(60, 220); c.lineTo(140, 220); c.lineTo(180, H); c.lineTo(20, H);
    c.fill();

    // 床
    r.roundRect(120, 170, 60, 50, 4, '#5a3a2a');   // 床身
    r.roundRect(118, 158, 64, 16, 4, '#e8e0d0');   // 床头板
    r.roundRect(124, 160, 52, 8, 2, '#c0b0a0');    // 枕头区
    // 床头柜
    r.roundRect(190, 180, 28, 40, 3, '#4a3a2a');
    // 小夜灯
    c.fillStyle = 'rgba(255,200,100,0.6)';
    c.beginPath(); c.arc(204, 178, 4, 0, Math.PI * 2); c.fill();
    c.fillStyle = 'rgba(255,200,100,0.06)';
    c.beginPath(); c.arc(204, 178, 40, 0, Math.PI * 2); c.fill();

    // 植物
    r.roundRect(520, 160, 20, 60, 2, '#3a4a3a');  // 花盆
    c.fillStyle = '#3a5a3a';
    c.beginPath(); c.arc(530, 148, 16, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#4a7a4a';
    c.beginPath(); c.arc(525, 142, 10, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#5a8a5a';
    c.beginPath(); c.arc(535, 140, 8, 0, Math.PI * 2); c.fill();
  },

  HOME_MORNING(r) {
    const c = r.ctx;
    // 墙壁暖色
    const wg = c.createLinearGradient(0, 0, 0, 220);
    wg.addColorStop(0, '#e8e0d0'); wg.addColorStop(1, '#d8d0c0');
    c.fillStyle = wg; c.fillRect(0, 0, W, 220);
    // 地板
    const fg = c.createLinearGradient(0, 220, 0, H);
    fg.addColorStop(0, '#3a3228'); fg.addColorStop(1, '#2a2218');
    c.fillStyle = fg; c.fillRect(0, 220, W, H - 220);

    // 大窗户 + 阳光
    r.roundRect(40, 40, 100, 80, 4, '#87CEEB');
    c.fillStyle = '#c0b0a0';
    c.fillRect(88, 40, 4, 80);
    c.fillRect(40, 78, 100, 3);
    // 阳光射入
    c.fillStyle = 'rgba(255,240,180,0.08)';
    c.beginPath();
    c.moveTo(40, 120); c.lineTo(140, 120); c.lineTo(220, H); c.lineTo(0, H);
    c.fill();

    // 厨房区域
    r.roundRect(360, 120, 160, 100, 0, '#d0c8b8');
    // 台面
    r.roundRect(380, 140, 40, 30, 3, '#f0f0e8');
    // 咖啡机
    r.roundRect(400, 120, 20, 22, 3, '#555');
    c.fillStyle = '#f0e8a0';
    c.beginPath(); c.arc(410, 125, 3, 0, Math.PI * 2); c.fill(); // 小灯
    // 冰箱
    r.roundRect(490, 120, 30, 100, 3, '#b0a898');
    r.roundRect(494, 125, 22, 40, 2, '#a09888');
    c.fillStyle = '#888'; c.fillRect(506, 140, 2, 10); // 把手
  },

  HOME_EVENING(r) {
    const c = r.ctx;
    // 暖色夜墙
    const wg = c.createLinearGradient(0, 0, 0, 220);
    wg.addColorStop(0, '#2a2030'); wg.addColorStop(1, '#1e1a28');
    c.fillStyle = wg; c.fillRect(0, 0, W, 220);
    // 地板
    const fg = c.createLinearGradient(0, 220, 0, H);
    fg.addColorStop(0, '#3a3228'); fg.addColorStop(1, '#2a2218');
    c.fillStyle = fg; c.fillRect(0, 220, W, H - 220);

    // 电视
    r.roundRect(280, 80, 100, 60, 4, '#1a1a2a');
    r.roundRect(284, 84, 92, 52, 2, '#3a4a5a');
    // 电视动态色彩
    const hue = (r.time * 0.5) % 360;
    c.fillStyle = `hsla(${hue},40%,50%,0.15)`;
    c.fillRect(284, 84, 92, 52);
    // 电视柜
    r.roundRect(260, 144, 140, 16, 3, '#4a3a2a');
    // 电视光
    c.fillStyle = `rgba(100,130,180,0.05)`;
    c.beginPath();
    c.moveTo(280, 160); c.lineTo(380, 160); c.lineTo(420, 360); c.lineTo(240, 360);
    c.fill();

    // 沙发
    r.roundRect(240, 180, 160, 40, 6, '#5a4a3a');
    r.roundRect(228, 170, 20, 60, 4, '#5a4a3a');
    r.roundRect(392, 170, 20, 60, 4, '#5a4a3a');
    // 抱枕
    r.roundRect(260, 178, 24, 22, 4, '#8a6a5a');
    r.roundRect(360, 180, 20, 18, 4, '#6a7a8a');

    // 落地灯
    r.roundRect(180, 100, 4, 120, 1, '#888');
    c.fillStyle = 'rgba(255,200,100,0.5)';
    c.beginPath(); c.arc(182, 96, 16, 0, Math.PI * 2); c.fill();
    c.fillStyle = 'rgba(255,200,100,0.06)';
    c.beginPath(); c.arc(182, 96, 80, 0, Math.PI * 2); c.fill();

    // 猫
    const catX = 160 + Math.sin(r.time * 0.02) * 8;
    c.fillStyle = '#f5a623';
    c.beginPath(); c.ellipse(catX, 260, 16, 10, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(catX + 14, 250, 6, 0, Math.PI * 2); c.fill();
    // 耳朵
    c.beginPath(); c.moveTo(catX + 10, 246); c.lineTo(catX + 8, 238); c.lineTo(catX + 14, 244); c.fill();
    c.beginPath(); c.moveTo(catX + 18, 244); c.lineTo(catX + 20, 238); c.lineTo(catX + 22, 246); c.fill();
    // 眼睛
    c.fillStyle = '#333';
    c.beginPath(); c.arc(catX + 12, 250, 1.5, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(catX + 17, 250, 1.5, 0, Math.PI * 2); c.fill();
    // 尾巴
    c.strokeStyle = '#f5a623'; c.lineWidth = 3; c.lineCap = 'round';
    c.beginPath();
    c.moveTo(catX - 14, 256);
    c.quadraticCurveTo(catX - 24, 240 + Math.sin(r.time * 0.04) * 5, catX - 18, 234);
    c.stroke();
  },

  HOME_WEEKEND_LAZY(r) {
    SCENE_RENDERERS.HOME_SLEEPING(r);
    r.ctx.fillStyle = 'rgba(200,200,180,0.1)';
    r.ctx.fillRect(0, 0, W, H);
  },

  COMMUTE_TO_WORK(r) {
    const c = r.ctx;
    // 地铁车厢
    const wg = c.createLinearGradient(0, 0, 0, 260);
    wg.addColorStop(0, '#e8e4e0'); wg.addColorStop(1, '#d8d4d0');
    c.fillStyle = wg; c.fillRect(0, 0, W, 260);
    // 地板
    c.fillStyle = '#888'; c.fillRect(0, 260, W, H - 260);
    c.fillStyle = '#666'; c.fillRect(0, 280, W, H - 280);

    // 大车窗
    for (let i = 0; i < 4; i++) {
      const wx = 40 + i * 150;
      r.roundRect(wx, 40, 100, 80, 4, '#87CEEB');
      c.fillStyle = '#d0ccc8';
      c.fillRect(wx - 3, 38, 106, 84);
      c.fillStyle = '#87CEEB';
      r.roundRect(wx, 40, 100, 80, 4, '#87CEEB');
    }

    // 把手
    c.strokeStyle = '#999'; c.lineWidth = 2;
    for (let i = 0; i < 8; i++) {
      const hx = 60 + i * 70;
      c.beginPath(); c.moveTo(hx, 140); c.lineTo(hx, 200); c.stroke();
      c.fillStyle = '#aaa';
      c.beginPath(); c.arc(hx, 136, 6, 0, Math.PI * 2); c.fill();
    }

    // 门
    r.roundRect(0, 80, 12, 140, 2, '#d0ccc8');
    r.roundRect(W - 12, 80, 12, 140, 2, '#d0ccc8');

    // 运动线条
    const offset = (r.time * 2) % 40;
    c.fillStyle = 'rgba(150,150,150,0.2)';
    for (let i = 0; i < 10; i++) c.fillRect(0, offset + i * 40, W, 1);

    // LED 线路图
    r.roundRect(490, 50, 120, 50, 3, '#1a1a2a');
    c.fillStyle = '#4a8af5';
    for (let i = 0; i < 4; i++) {
      c.beginPath(); c.arc(520 + i * 25, 75, 4, 0, Math.PI * 2); c.fill();
    }
    c.strokeStyle = '#4a8af5'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(520, 75); c.lineTo(545, 75); c.lineTo(570, 75); c.lineTo(595, 75); c.stroke();
  },

  COMMUTE_TO_HOME(r) {
    SCENE_RENDERERS.COMMUTE_TO_WORK(r);
    r.ctx.fillStyle = 'rgba(20,20,40,0.35)';
    r.ctx.fillRect(0, 0, W, H);
  },

  OFFICE_WORKING(r) {
    const c = r.ctx;
    // 明亮办公室
    const wg = c.createLinearGradient(0, 0, 0, 220);
    wg.addColorStop(0, '#f5f5f0'); wg.addColorStop(1, '#e8e5e0');
    c.fillStyle = wg; c.fillRect(0, 0, W, 220);
    // 地板
    c.fillStyle = '#e0ddd5'; c.fillRect(0, 220, W, H - 220);

    // 大落地窗
    r.roundRect(0, 20, W, 100, 0, '#c0d8e8');
    // 窗格
    c.fillStyle = '#ddd';
    for (let i = 0; i < 10; i++) c.fillRect(i * 66 + 5, 20, 2, 100);
    // 天际线
    c.fillStyle = 'rgba(100,120,140,0.2)';
    for (let i = 0; i < 5; i++) {
      const bw = 30 + i * 15;
      c.fillRect(i * 130 + 20, 100 - 30 - i * 10, bw, 30 + i * 10);
    }

    // 工位（3x2）
    for (let row = 0; row < 2; row++) {
      for (let col = 0; col < 3; col++) {
        const dx = 80 + col * 200;
        const dy = 140 + row * 50;
        // 桌面
        r.roundRect(dx, dy, 120, 6, 2, '#8a7a6a');
        // 桌腿
        c.fillStyle = '#7a6a5a'; c.fillRect(dx + 10, dy + 6, 4, 30); c.fillRect(dx + 106, dy + 6, 4, 30);
        // 显示器
        r.roundRect(dx + 30, dy - 30, 60, 28, 3, '#555');
        r.roundRect(dx + 33, dy - 27, 54, 22, 2, '#4a6a8a');
        // 显示器支架
        c.fillStyle = '#555'; c.fillRect(dx + 57, dy - 3, 6, 6);
        // 键盘
        r.roundRect(dx + 35, dy + 1, 50, 4, 1, '#888');
        // 屏幕内容微光
        c.fillStyle = 'rgba(100,180,255,0.05)';
        c.fillRect(dx + 33, dy - 27, 54, 22);
      }
    }
  },

  OFFICE_MEETING(r) {
    SCENE_RENDERERS.OFFICE_WORKING(r);
    const c = r.ctx;
    // 会议桌
    r.roundRect(160, 170, 320, 80, 6, '#8a7a6a');
    r.roundRect(160, 166, 320, 8, 4, '#9a8a7a');
    // 投影幕
    r.roundRect(200, 50, 240, 120, 3, '#fff');
    c.fillStyle = '#e8e8e0';
    c.fillRect(202, 52, 236, 116);
    c.fillStyle = '#333'; c.font = '14px sans-serif'; c.fillText('Q2 目标复盘', 260, 115);
  },

  OFFICE_LUNCH(r) {
    const c = r.ctx;
    // 外面觅食街道
    c.fillStyle = '#e8e0d0'; c.fillRect(0, 0, W, 180);
    c.fillStyle = '#d0c8b8'; c.fillRect(0, 180, W, H - 180);

    // 建筑背景
    r.roundRect(20, 60, 150, 120, 0, '#c0b8a8');
    r.roundRect(180, 40, 120, 140, 0, '#b8b0a0');
    r.roundRect(470, 50, 140, 130, 0, '#c8c0b0');

    // 餐厅
    r.roundRect(200, 60, 240, 100, 6, '#f0e8d0');
    r.roundRect(200, 50, 240, 20, 6, '#e74c3c');
    c.fillStyle = '#fff'; c.font = '14px sans-serif'; c.fillText('🍜 味千拉面', 280, 66);

    // 户外桌椅
    for (let i = 0; i < 3; i++) {
      const tx = 100 + i * 180;
      r.roundRect(tx, 200, 60, 6, 2, '#8a7a6a');
      // 遮阳伞
      c.fillStyle = i % 2 === 0 ? 'rgba(230,80,60,0.7)' : 'rgba(60,140,200,0.7)';
      c.beginPath(); c.arc(tx + 30, 196, 30, Math.PI, Math.PI * 2); c.fill();
      c.fillStyle = '#888'; c.fillRect(tx + 28, 196, 4, 20);
    }

    // 人行道
    c.fillStyle = '#c0b8a8'; c.fillRect(0, 280, W, 10);
  },

  CAFE(r) {
    const c = r.ctx;
    // 温暖咖啡色
    const wg = c.createLinearGradient(0, 0, 0, 220);
    wg.addColorStop(0, '#f0e8d0'); wg.addColorStop(1, '#e0d8c0');
    c.fillStyle = wg; c.fillRect(0, 0, W, 220);
    // 木地板
    c.fillStyle = '#c0a880'; c.fillRect(0, 220, W, H - 220);
    // 木纹
    c.strokeStyle = 'rgba(0,0,0,0.05)'; c.lineWidth = 1;
    for (let i = 0; i < 10; i++) { c.beginPath(); c.moveTo(0, 220 + i * 14); c.lineTo(W, 220 + i * 14); c.stroke(); }

    // 大窗
    r.roundRect(40, 30, 240, 120, 4, '#d8d0c0');
    r.roundRect(44, 34, 232, 112, 2, '#e8e0d0');
    // 窗外树影
    c.fillStyle = 'rgba(100,160,80,0.3)';
    c.beginPath(); c.arc(100, 50, 30, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(250, 60, 20, 0, Math.PI * 2); c.fill();

    // 吧台
    r.roundRect(0, 120, 200, 100, 0, '#6a4a3a');
    r.roundRect(0, 115, 200, 12, 4, '#7a5a4a');
    // 咖啡机
    r.roundRect(30, 90, 24, 28, 3, '#555');
    c.fillStyle = '#e74c3c'; c.beginPath(); c.arc(42, 96, 3, 0, Math.PI * 2); c.fill();
    // 杯子架
    for (let i = 0; i < 4; i++) {
      c.fillStyle = i % 2 === 0 ? '#fff' : '#e8d8c8';
      c.beginPath(); c.arc(80 + i * 16, 100, 5, 0, Math.PI * 2); c.fill();
    }
    // 菜单板
    r.roundRect(60, 40, 80, 50, 3, '#2a2a2a');
    c.fillStyle = '#e8d8a8'; c.font = '10px sans-serif';
    c.fillText('Latte    ¥28', 68, 58);
    c.fillText('Mocha    ¥32', 68, 72);
    c.fillText('Matcha   ¥30', 68, 84);

    // 桌子
    for (let i = 0; i < 2; i++) {
      const tx = 320 + i * 150;
      r.roundRect(tx, 190, 100, 6, 3, '#8a7a6a');
      // 桌腿
      c.fillStyle = '#7a6a5a'; c.fillRect(tx + 45, 196, 10, 30);
      // 桌上咖啡杯
      c.fillStyle = '#fff';
      c.beginPath(); c.arc(tx + 30, 188, 7, 0, Math.PI * 2); c.fill();
      c.fillStyle = '#6a4a3a';
      c.beginPath(); c.arc(tx + 30, 188, 5, 0, Math.PI * 2); c.fill();
      // 蒸汽
      c.strokeStyle = 'rgba(255,255,255,0.3)'; c.lineWidth = 1;
      const sOff = Math.sin(r.time * 0.04 + i) * 2;
      c.beginPath(); c.moveTo(tx + 28, 182); c.quadraticCurveTo(tx + 26, 174 + sOff, tx + 30, 168); c.stroke();
    }

    // 吊灯
    for (let i = 0; i < 3; i++) {
      const lx = 100 + i * 200;
      c.strokeStyle = '#999'; c.lineWidth = 1;
      c.beginPath(); c.moveTo(lx, 0); c.lineTo(lx, 30); c.stroke();
      c.fillStyle = 'rgba(255,200,100,0.7)';
      c.beginPath(); c.arc(lx, 34, 8, 0, Math.PI * 2); c.fill();
      c.fillStyle = 'rgba(255,200,100,0.06)';
      c.beginPath(); c.arc(lx, 34, 60, 0, Math.PI * 2); c.fill();
    }
  },

  PARK(r) {
    const c = r.ctx;
    // 天空渐变
    const sg = c.createLinearGradient(0, 0, 0, 200);
    sg.addColorStop(0, '#6ab7e8'); sg.addColorStop(1, '#a8d8f0');
    c.fillStyle = sg; c.fillRect(0, 0, W, 200);

    // 云
    const drawCloud = (cx, cy, s) => {
      c.fillStyle = 'rgba(255,255,255,0.85)';
      c.beginPath(); c.arc(cx, cy, 18 * s, 0, Math.PI * 2); c.fill();
      c.beginPath(); c.arc(cx - 15 * s, cy + 4, 12 * s, 0, Math.PI * 2); c.fill();
      c.beginPath(); c.arc(cx + 16 * s, cy + 3, 14 * s, 0, Math.PI * 2); c.fill();
      c.beginPath(); c.arc(cx + 5 * s, cy - 8 * s, 10 * s, 0, Math.PI * 2); c.fill();
    };
    const cloudOff = (r.time * 0.1) % W;
    drawCloud(100 + cloudOff % 500, 50, 1.2);
    drawCloud(350 + (cloudOff * 0.7) % 500, 35, 0.9);
    drawCloud(550 + (cloudOff * 0.5) % 500, 60, 1.0);

    // 草地
    const gg = c.createLinearGradient(0, 200, 0, H);
    gg.addColorStop(0, '#5aaa4a'); gg.addColorStop(1, '#3a8a3a');
    c.fillStyle = gg; c.fillRect(0, 200, W, H - 200);
    // 草地纹理
    c.fillStyle = 'rgba(80,180,60,0.3)';
    for (let i = 0; i < 40; i++) {
      c.fillRect(Math.random() * W, 200 + Math.random() * 160, 3, 6);
    }

    // 小路
    c.fillStyle = '#c0b898';
    c.beginPath();
    c.moveTo(260, 200); c.lineTo(380, 200); c.lineTo(400, H); c.lineTo(240, H);
    c.fill();
    c.fillStyle = 'rgba(0,0,0,0.05)';
    c.beginPath();
    c.moveTo(280, 200); c.lineTo(360, 200); c.lineTo(380, H); c.lineTo(260, H);
    c.fill();

    // 树
    const drawTree = (x, y, s) => {
      // 树干
      c.fillStyle = '#5a3a1a';
      c.beginPath(); c.moveTo(x - 5 * s, y); c.lineTo(x + 5 * s, y);
      c.lineTo(x + 3 * s, y + 40 * s); c.lineTo(x - 3 * s, y + 40 * s); c.fill();
      // 树冠（多层圆）
      c.fillStyle = '#3a7a3a';
      c.beginPath(); c.arc(x, y - 8 * s, 22 * s, 0, Math.PI * 2); c.fill();
      c.fillStyle = '#4a8a4a';
      c.beginPath(); c.arc(x - 8 * s, y, 16 * s, 0, Math.PI * 2); c.fill();
      c.beginPath(); c.arc(x + 10 * s, y - 2 * s, 14 * s, 0, Math.PI * 2); c.fill();
      c.fillStyle = '#5a9a5a';
      c.beginPath(); c.arc(x + 2 * s, y - 14 * s, 12 * s, 0, Math.PI * 2); c.fill();
    };
    drawTree(60, 150, 1.2);
    drawTree(200, 140, 1.5);
    drawTree(440, 148, 1.3);
    drawTree(560, 155, 1.1);

    // 长椅
    r.roundRect(290, 230, 60, 6, 2, '#6a4a2a');
    r.roundRect(296, 236, 4, 14, 1, '#6a4a2a');
    r.roundRect(340, 236, 4, 14, 1, '#6a4a2a');
    // 背板
    r.roundRect(292, 220, 56, 4, 1, '#6a4a2a');

    // 小花
    const flowerColors = ['#e74c3c', '#f39c12', '#e91e63', '#9b59b6'];
    for (let i = 0; i < 8; i++) {
      c.fillStyle = flowerColors[i % 4];
      c.beginPath(); c.arc(140 + i * 50, 240 + (i % 3) * 20, 3, 0, Math.PI * 2); c.fill();
      c.fillStyle = '#4a8a3a';
      c.fillRect(140 + i * 50 - 1, 244 + (i % 3) * 20, 2, 8);
    }
  },

  SUPERMARKET(r) {
    const c = r.ctx;
    // 明亮超市
    c.fillStyle = '#f0f0e8'; c.fillRect(0, 0, W, 220);
    c.fillStyle = '#e0ddd5'; c.fillRect(0, 220, W, H - 220);

    // 天花板灯
    for (let i = 0; i < 5; i++) {
      const lx = 60 + i * 130;
      r.roundRect(lx, 0, 60, 10, 3, '#f8f8f0');
      c.fillStyle = 'rgba(255,255,200,0.06)';
      c.fillRect(lx - 20, 0, 100, 220);
    }

    // 货架（3排）
    const shelfColors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#e67e22', '#1abc9c', '#c0392b'];
    for (let i = 0; i < 3; i++) {
      const sx = 40 + i * 200;
      // 货架框架
      r.roundRect(sx, 100, 160, 120, 3, '#d0d0c0');
      // 层板 + 商品
      for (let j = 0; j < 4; j++) {
        const ly = 105 + j * 28;
        c.fillStyle = '#c0c0b0'; c.fillRect(sx + 4, ly, 152, 3);
        for (let k = 0; k < 6; k++) {
          const ci = (i * 4 + j + k) % shelfColors.length;
          c.fillStyle = shelfColors[ci];
          r.roundRect(sx + 8 + k * 24, ly - 18, 20, 16, 2, shelfColors[ci]);
        }
      }
    }

    // 价格标签（小细节）
    c.fillStyle = '#ff0'; c.font = '8px sans-serif';
    c.fillText('¥12.9', 52, 96); c.fillText('¥8.5', 252, 96); c.fillText('¥25.0', 452, 96);
  },

  STREET_WANDERING(r) {
    const c = r.ctx;
    // 天空
    const sg = c.createLinearGradient(0, 0, 0, 180);
    sg.addColorStop(0, '#6ab7e8'); sg.addColorStop(1, '#a8d8f0');
    c.fillStyle = sg; c.fillRect(0, 0, W, 180);

    // 云
    c.fillStyle = 'rgba(255,255,255,0.8)';
    const cOff = (r.time * 0.08) % W;
    c.beginPath(); c.arc(100 + cOff % 600, 40, 20, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(120 + cOff % 600, 36, 14, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(400 + (cOff * 0.6) % 600, 55, 16, 0, Math.PI * 2); c.fill();

    // 建筑
    const drawBuilding = (x, w, h, color) => {
      r.roundRect(x, 180 - h, w, h, 0, color);
      for (let row = 0; row < Math.floor(h / 32); row++) {
        for (let col = 0; col < Math.floor(w / 32); col++) {
          c.fillStyle = (row + col) % 2 === 0 ? 'rgba(42,58,90,0.6)' : 'rgba(240,232,208,0.5)';
          c.fillRect(x + 6 + col * 32, 180 - h + 10 + row * 32, 18, 18);
        }
      }
    };
    drawBuilding(0, 100, 160, '#8a8090');
    drawBuilding(120, 80, 120, '#9a9080');
    drawBuilding(400, 120, 180, '#7a8090');
    drawBuilding(540, 100, 110, '#a09888');

    // 招牌
    r.roundRect(130, 100, 70, 20, 3, '#e74c3c');
    c.fillStyle = '#fff'; c.font = '11px sans-serif'; c.fillText('奶茶店', 142, 114);
    r.roundRect(420, 80, 80, 20, 3, '#3498db');
    c.fillStyle = '#fff'; c.fillText('便利蜂', 435, 94);

    // 人行道
    c.fillStyle = '#bbb'; c.fillRect(0, 220, W, 20);
    // 斑马线
    for (let i = 0; i < 6; i++) {
      c.fillStyle = '#fff';
      c.fillRect(280 + i * 18, 220, 10, 20);
    }
    // 马路
    c.fillStyle = '#666'; c.fillRect(0, 240, W, 80);
    // 路灯
    c.fillStyle = '#555'; c.fillRect(300, 80, 4, 140);
    c.fillStyle = '#f0e8a0';
    c.beginPath(); c.arc(302, 76, 12, 0, Math.PI * 2); c.fill();
    c.fillStyle = 'rgba(240,232,160,0.05)';
    c.beginPath(); c.arc(302, 76, 60, 0, Math.PI * 2); c.fill();
  },

  FRIEND_HANGOUT(r) {
    SCENE_RENDERERS.CAFE(r);
    r.ctx.fillStyle = 'rgba(255,180,100,0.04)';
    r.ctx.fillRect(0, 0, W, H);
  },

  OVERTIME(r) {
    SCENE_RENDERERS.OFFICE_WORKING(r);
    const c = r.ctx;
    c.fillStyle = 'rgba(10,10,30,0.55)';
    c.fillRect(0, 0, W, H);
    // 只有主角工位亮
    c.fillStyle = 'rgba(255,255,200,0.08)';
    c.beginPath(); c.arc(300, 170, 80, 0, Math.PI * 2); c.fill();
    // 窗外夜景
    c.fillStyle = '#1a2a4a';
    c.fillRect(0, 20, W, 100);
    c.fillStyle = 'rgba(255,200,100,0.4)';
    for (let i = 0; i < 12; i++) {
      c.fillRect(30 + i * 50 + Math.random() * 20, 40 + Math.random() * 60, 3, 3);
    }
  },

};
