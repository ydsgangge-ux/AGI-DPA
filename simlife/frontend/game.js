/**
 * SimLife 主循环 v2
 */

const API_BASE = '';

const Game = {
  renderer: null,
  currentScene: '',
  character: null,
  npcCards: [],
  initialized: false,
  pollInterval: null,
  _activeNpcIds: [],

  async init() {
    UI.init();

    const canvas = document.getElementById('game-canvas');
    this.renderer = new Renderer(canvas);

    try {
      const resp = await fetch(API_BASE + '/api/character');
      const data = await resp.json();

      if (data.initialized) {
        this.character = data.card;
        this.initialized = true;
        UI.hideSetup();
        this.startLoop();
      } else {
        UI.showSetup();
      }
    } catch (e) {
      console.error('Failed to check status:', e);
      UI.showSetup();
    }
  },

  onCharacterReady(card) {
    this.character = card;
    this.initialized = true;
    this.startLoop();
  },

  startLoop() {
    this.render();
    this.poll();
    this.pollInterval = setInterval(() => this.poll(), 10000);
  },

  render() {
    if (!this.character) {
      requestAnimationFrame(() => this.render());
      return;
    }

    const pixel = this.character.pixel_appearance || {};
    const mainChar = {
      hairColor: pixel.hair_color || '#4A3728',
      outfitColor: pixel.default_outfit_color || '#F5F0E8',
    };

    const activeNpcs = [];
    if (this.npcCards) {
      this._activeNpcIds.forEach(id => {
        const npc = this.npcCards.find(n => n.id === id);
        if (npc) {
          activeNpcs.push({
            variant: npc.pixel_variant ?
              parseInt(npc.pixel_variant.replace(/\D/g, '')) || 0 : 0,
          });
        }
      });
    }

    const bgCount = this._getBgNpcCount(this.currentScene);

    this.renderer.drawScene(
      this.currentScene || 'HOME_EVENING',
      mainChar,
      activeNpcs,
      bgCount
    );

    requestAnimationFrame(() => this.render());
  },

  async poll() {
    if (!this.initialized) return;

    try {
      const resp = await fetch(API_BASE + '/api/world/state');
      const state = await resp.json();

      if (state.error) return;

      const sceneChanged = state.scene !== this.currentScene;

      const now = new Date();
      const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
      UI.updateTopBar({
        city: this.character?.basic?.city || '',
        weekday: weekdays[now.getDay()],
        time: now.toTimeString().slice(0, 5),
        weather: state.weather || '⛅',
      });
      UI.updateMood(state.mood);
      UI.updateActivity(state.activity, state.scene_label || '');

      if (state.latest_log) {
        UI.updateLogs(state.latest_log);
      }

      // 天气同步给渲染器
      if (state.weather && this.renderer) {
        const wMap = { 'rainy': 'rainy', 'heavy_rain': 'heavy_rain', 'snow': 'snow', 'cloudy': 'cloudy', 'sunny': 'cloudy' };
        this.renderer.setWeather(wMap[state.weather] || 'cloudy');
      }

      if (sceneChanged && this.currentScene) {
        this.renderer.startFade(() => {
          this.currentScene = state.scene;
        });
      } else {
        this.currentScene = state.scene;
      }

      this._activeNpcIds = state.active_npcs || [];

    } catch (e) {
      console.error('Poll error:', e);
    }
  },

  _getBgNpcCount(scene) {
    const counts = {
      'COMMUTE_TO_WORK': 4,
      'COMMUTE_TO_HOME': 2,
      'OFFICE_WORKING': 1,
      'OFFICE_LUNCH': 3,
      'STREET_WANDERING': 3,
      'CAFE': 1,
      'PARK': 2,
      'SUPERMARKET': 3,
    };
    return counts[scene] || 0;
  },
};

document.addEventListener('DOMContentLoaded', () => {
  Game.init();
});
