# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os
import json
from PySide6.QtCore import QTranslator, QLocale, QObject, Signal

class Translator(QObject):
    """国际化翻译管理器"""
    
    _instance = None
    _translator = None
    _app = None
    _current_language = 'zh_CN'
    language_changed = Signal(str)
    
    # 支持的语言列表
    SUPPORTED_LANGUAGES = {
        'zh_CN': {'name': '简体中文', 'flag': '🇨🇳'},
        'en_US': {'name': 'English', 'flag': '🇺🇸'}
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        super().__init__()
        if not hasattr(self, '_initialized'):
            self._translator = QTranslator()
            self._translations = {}
            self._load_translations()
            self._initialized = True
    
    def _load_translations(self):
        """加载翻译文件"""
        locales_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locales')
        
        for lang_code in self.SUPPORTED_LANGUAGES.keys():
            translation_file = os.path.join(locales_dir, f'{lang_code}.json')
            if os.path.exists(translation_file):
                try:
                    with open(translation_file, 'r', encoding='utf-8') as f:
                        self._translations[lang_code] = json.load(f)
                except Exception as e:
                    print(f"Error loading translation file {translation_file}: {e}")
            else:
                self._translations[lang_code] = {}
    
    def set_application(self, app):
        """设置 QApplication 实例"""
        self._app = app
    
    def set_language(self, lang_code):
        """设置当前语言"""
        if lang_code not in self.SUPPORTED_LANGUAGES:
            return False
        
        old_language = self._current_language
        self._current_language = lang_code
        
        if self._app:
            self._app.removeTranslator(self._translator)
            
            locale = QLocale(lang_code)
            qt_translator = QTranslator()
            if qt_translator.load(locale, "qtbase_", directory=""):
                self._app.installTranslator(qt_translator)
            
            self._app.installTranslator(self._translator)
        
        self.language_changed.emit(lang_code)
        return True
    
    def get_current_language(self):
        """获取当前语言代码"""
        return self._current_language
    
    def get_supported_languages(self):
        """获取支持的语言列表"""
        return self.SUPPORTED_LANGUAGES
    
    def tr(self, context, key, default=None, **kwargs):
        if default is None:
            default = key
        
        translation_dict = self._translations.get(self._current_language, {})
        context_dict = translation_dict.get(context, {})
        text = context_dict.get(key, default)
        
        if kwargs and isinstance(text, str):
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass
        
        return text
    
    def reload_translations(self):
        """重新加载翻译文件"""
        self._load_translations()
        if self._app:
            self._app.removeTranslator(self._translator)
            self._app.installTranslator(self._translator)

translator = Translator()
def _(context, key, default=None, **kwargs):
    """快捷翻译函数"""
    return translator.tr(context, key, default, **kwargs)