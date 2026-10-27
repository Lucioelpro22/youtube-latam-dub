import asyncio
import base64
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import server
import translator_service as translator
from fastapi import HTTPException

class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_translation_does_not_block_status(self):
        def slow_translation(**kwargs):
            time.sleep(0.15)
            return 'Hola'
        async def speech(**kwargs):
            return b'audio'
        with patch.object(server, 'translate_sentence', slow_translation), patch.object(server, 'generate_speech', speech):
            task = asyncio.create_task(server.process_dub(server.DubRequest(text='Hello')))
            await asyncio.sleep(0.02)
            self.assertFalse(task.done(), 'Translation should still be working while server responds')
            self.assertEqual((await server.status())['status'], 'online')
            result = await task
            self.assertEqual(base64.b64decode(result.audio_base64), b'audio')
            self.assertGreaterEqual(result.timings_ms['translation'], 100)

    async def test_empty_speech_is_an_error(self):
        async def empty_speech(**kwargs): return b''
        with patch.object(server, 'translate_sentence', return_value='Hola'), patch.object(server, 'generate_speech', empty_speech):
            with self.assertRaises(HTTPException) as error:
                await server.process_dub(server.DubRequest(text='Hello'))
            self.assertEqual(error.exception.status_code, 502)

    async def test_translation_failure_does_not_synthesize_original_text(self):
        async def unexpected_speech(**kwargs): self.fail('Speech must not run after failed translation')
        with patch.object(server, 'translate_sentence', side_effect=RuntimeError('offline')), patch.object(server, 'generate_speech', unexpected_speech):
            with self.assertRaises(HTTPException) as error:
                await server.process_dub(server.DubRequest(text='Hello'))
            self.assertEqual(error.exception.status_code, 500)

    async def test_provider_limit_is_503_with_retry_after(self):
        failure = translator.TranslationUnavailable("Límite alcanzado", "rate_limited", 60)
        with patch.object(server, 'translate_sentence', side_effect=failure):
            with self.assertRaises(HTTPException) as error:
                await server.process_dub(server.DubRequest(text='Hello'))
            self.assertEqual(error.exception.status_code, 503)
            self.assertEqual(error.exception.headers['Retry-After'], '60')
            self.assertEqual(error.exception.detail['code'], 'rate_limited')

    async def test_timeout_returns_504(self):
        def slow_translation(**kwargs): time.sleep(5.2); return 'Hola'
        with patch.object(server, 'translate_sentence', slow_translation):
            with self.assertRaises(HTTPException) as error:
                await server.process_dub(server.DubRequest(text='Hello'))
            self.assertEqual(error.exception.status_code, 504)

class TranslatorTests(unittest.TestCase):
    def setUp(self):
        translator.TRANSLATION_CACHE.clear()
        translator.PROVIDER_COOLDOWNS.clear()
        local_disabled = patch.object(translator.local_translator, 'available', return_value=False)
        local_disabled.start()
        self.addCleanup(local_disabled.stop)

    def test_spanish_captions_skip_external_translation(self):
        text = "Hoy vamos a aprender cómo resolver estas tareas complejas paso a paso."
        with patch.object(translator, 'detect_source', return_value='es'), patch.object(translator, 'GoogleTranslator') as google:
            self.assertEqual(translator.translate_fallback(text), text)
            google.assert_not_called()

    def test_mymemory_fallback_only_for_confident_english(self):
        with patch.object(translator, 'detect_source', return_value='en'), patch.object(translator, 'GoogleTranslator') as google, patch.object(translator, 'MyMemoryTranslator') as memory:
            google.return_value.translate.side_effect = RuntimeError('rate limited')
            memory.return_value.translate.return_value = 'Hola a todos'
            self.assertEqual(translator.translate_fallback('Hello everyone and welcome back today'), 'Hola a todos')
            memory.assert_called_once_with(source='english', target='spanish latin america')

    def test_ambiguous_source_is_not_assumed_english(self):
        with patch.object(translator, 'detect_source', return_value=None), patch.object(translator, 'GoogleTranslator') as google, patch.object(translator, 'MyMemoryTranslator') as memory:
            google.return_value.translate.side_effect = RuntimeError('rate limited')
            with self.assertRaises(RuntimeError): translator.translate_fallback('Hola')
            memory.assert_not_called()

    def test_failures_are_not_cached(self):
        with patch.object(translator, 'translate_fallback', side_effect=[RuntimeError('offline'), 'Hola']):
            with self.assertRaises(RuntimeError): translator.translate_sentence('Hello')
            self.assertEqual(translator.translate_sentence('Hello'), 'Hola')

    def test_translation_workers_are_bounded(self):
        translator.PROVIDER_SLOTS.acquire(); translator.PROVIDER_SLOTS.acquire()
        try:
            with self.assertRaises(RuntimeError): translator.translate_sentence('Hello')
        finally:
            translator.PROVIDER_SLOTS.release(); translator.PROVIDER_SLOTS.release()

    def test_rate_limited_provider_is_not_called_again_during_cooldown(self):
        with patch.object(translator, 'GoogleTranslator') as google:
            google.return_value.translate.side_effect = translator.TooManyRequests()
            for _ in range(10):
                with self.assertRaises(translator.TranslationUnavailable) as error:
                    translator.translate_fallback('short fragment')
                self.assertEqual(error.exception.code, 'rate_limited')
            self.assertEqual(google.return_value.translate.call_count, 1)

    def test_spanish_context_allows_short_fragments_without_network(self):
        context = 'Hoy vamos a aprender cómo resolver tareas complejas paso a paso.'
        with patch.object(translator, 'GoogleTranslator') as google:
            self.assertEqual(translator.translate_sentence('y actúa.', context=context), 'y actúa.')
            google.assert_not_called()

    def test_explicit_spanish_works_even_when_translation_workers_are_busy(self):
        translator.PROVIDER_SLOTS.acquire(); translator.PROVIDER_SLOTS.acquire()
        try:
            self.assertEqual(translator.translate_sentence('Hola', source_lang='es'), 'Hola')
        finally:
            translator.PROVIDER_SLOTS.release(); translator.PROVIDER_SLOTS.release()

    def test_provider_recovers_after_cooldown(self):
        with patch.object(translator.time, 'monotonic', return_value=100), patch.object(translator, 'GoogleTranslator') as google:
            google.return_value.translate.side_effect = translator.TooManyRequests()
            with self.assertRaises(translator.TranslationUnavailable): translator.translate_fallback('Hello')
        with patch.object(translator.time, 'monotonic', return_value=161), patch.object(translator, 'GoogleTranslator') as google:
            google.return_value.translate.return_value = 'Hola'
            self.assertEqual(translator.translate_fallback('Hello'), 'Hola')
            google.return_value.translate.assert_called_once()

@unittest.skipUnless(translator.local_translator.available(), 'Local model is not installed')
class LocalTranslationTests(unittest.TestCase):
    def setUp(self): translator.TRANSLATION_CACHE.clear()

    def test_english_translates_with_cloud_providers_unavailable(self):
        text = 'Today we are going to learn how to build an application.'
        with patch.object(translator, 'translate_fallback', side_effect=AssertionError('No network fallback allowed')):
            result = translator.translate_sentence(text, source_lang='en')
        self.assertNotEqual(result, text)
        self.assertIn('aplicaci', result.lower())
        self.assertIn('aprender', result.lower())

    def test_stale_spanish_setting_does_not_bypass_english_translation(self):
        text = 'You can use this tool to automate your work.'
        with patch.object(translator, 'translate_fallback', side_effect=AssertionError('No network fallback allowed')):
            result = translator.translate_sentence(text, source_lang='es', context=text)
        self.assertIn('herramienta', result.lower())
        self.assertNotEqual(result, text)

    def test_spanish_stays_spanish_even_after_english_video(self):
        text = 'Hoy vamos a aprender cómo resolver tareas complejas paso a paso.'
        self.assertEqual(translator.translate_sentence(text, source_lang='en'), text)

    def test_short_english_fragment_uses_local_model(self):
        with patch.object(translator, 'translate_fallback', side_effect=AssertionError('No network fallback allowed')):
            result = translator.translate_sentence('Thank you', source_lang='auto')
        self.assertIn('gracias', result.lower())

if __name__ == '__main__': unittest.main()
