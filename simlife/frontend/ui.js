/**
 * SimLife UI 管理 v2
 */

const UI = {
  $city: null,
  $weekday: null,
  $time: null,
  $weather: null,
  $moodEmoji: null,
  $moodBar: null,
  $moodValue: null,
  $activityText: null,
  $sceneTag: null,
  $logList: null,
  $setupOverlay: null,
  $mainUi: null,

  init() {
    this.$city = document.getElementById('disp-city');
    this.$weekday = document.getElementById('disp-weekday');
    this.$time = document.getElementById('disp-time');
    this.$weather = document.getElementById('disp-weather');
    this.$moodEmoji = document.getElementById('mood-emoji');
    this.$moodBar = document.getElementById('mood-bar');
    this.$moodValue = document.getElementById('mood-value');
    this.$activityText = document.getElementById('activity-text');
    this.$sceneTag = document.getElementById('scene-tag');
    this.$logList = document.getElementById('log-list');
    this.$setupOverlay = document.getElementById('setup-overlay');
    this.$mainUi = document.getElementById('main-ui');
  },

  showSetup() {
    this.$setupOverlay.style.display = 'flex';
    this.$mainUi.style.display = 'none';
  },

  hideSetup() {
    this.$setupOverlay.style.display = 'none';
    this.$mainUi.style.display = 'flex';
  },

  updateTopBar(data) {
    if (data.city) this.$city.textContent = data.city;
    if (data.weekday) this.$weekday.textContent = data.weekday;
    if (data.time) this.$time.textContent = data.time;
    if (data.weather) this.$weather.textContent = data.weather;
  },

  updateMood(mood) {
    const pct = Math.max(0, Math.min(100, mood));
    this.$moodBar.style.width = pct + '%';

    let color;
    if (pct >= 70) color = 'var(--mood-good)';
    else if (pct >= 40) color = 'var(--mood-mid)';
    else color = 'var(--mood-bad)';
    this.$moodBar.style.background = color;

    let emoji;
    if (pct >= 85) emoji = '😄';
    else if (pct >= 70) emoji = '😊';
    else if (pct >= 55) emoji = '🙂';
    else if (pct >= 40) emoji = '😐';
    else if (pct >= 25) emoji = '😔';
    else emoji = '😢';
    this.$moodEmoji.textContent = emoji;

    if (this.$moodValue) this.$moodValue.textContent = pct;
  },

  updateActivity(text, sceneLabel) {
    this.$activityText.textContent = text || '';
    if (this.$sceneTag && sceneLabel) {
      this.$sceneTag.textContent = sceneLabel;
    }
  },

  updateLogs(logs) {
    if (!logs || logs.length === 0) return;

    const existing = this.$logList.children.length;
    const newLogs = logs.slice(existing);

    for (const log of newLogs) {
      const item = document.createElement('div');
      item.className = 'log-item';
      item.innerHTML = `<span class="log-time">${log.time}</span><span class="log-event">${log.event}</span>`;
      this.$logList.appendChild(item);
    }

    const panel = document.getElementById('log-panel');
    panel.scrollTop = panel.scrollHeight;
  },

  clearLogs() {
    this.$logList.innerHTML = '';
  },

  setSetupStatus(text) {
    document.getElementById('setup-status').textContent = text;
  },

  setGenerateButton(enabled) {
    document.getElementById('btn-generate').disabled = !enabled;
  },
};

// 暴露全局函数
function skipSetup() {
  UI.hideSetup();
}

function toggleAllLogs() {
  // TODO: 展开全部日志的弹窗
}

async function generateWorld() {
  const anchor = {
    character_name: document.getElementById('inp-name').value.trim(),
    city: document.getElementById('inp-city').value,
    occupation_hint: document.getElementById('inp-occupation').value.trim(),
    age: parseInt(document.getElementById('inp-age').value) || 24,
    personality_word: document.getElementById('inp-personality').value.trim(),
  };

  if (!anchor.character_name) {
    UI.setSetupStatus('请填写角色名字');
    return;
  }

  UI.setSetupStatus('正在生成人物卡和世界... AI 可能耗时 10-30 秒');
  UI.setGenerateButton(false);

  try {
    const resp = await fetch('/api/setup/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ anchor }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '生成失败');
    }

    const data = await resp.json();
    UI.setSetupStatus('✅ 世界生成完成！');

    setTimeout(() => {
      UI.hideSetup();
      if (typeof Game !== 'undefined') {
        Game.onCharacterReady(data.card);
      }
    }, 800);

  } catch (e) {
    UI.setSetupStatus('❌ ' + e.message);
    UI.setGenerateButton(true);
  }
}
