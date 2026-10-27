from dishka import Provider, Scope, provide

from src.worker.letters.service import LettersService


class LettersProvider(Provider):
    letters_service = provide(LettersService, scope=Scope.REQUEST)
