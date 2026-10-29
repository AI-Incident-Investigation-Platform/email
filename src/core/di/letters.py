from dishka import Provider, Scope, provide

from src.worker.letters.latest import LatestLetters
from src.worker.letters.service import LettersService


class LettersProvider(Provider):
    latest_letters = provide(LatestLetters, scope=Scope.APP)
    letters_service = provide(LettersService, scope=Scope.REQUEST)
