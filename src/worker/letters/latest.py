from datetime import UTC, datetime

from src.worker.letters.dto import Letter, SeenLetter


class LatestLetters:
    """Самое новое письмо по каждому ключу вытеснения, которое видел под.

    Отправитель ставит одинаковый `collapse_key` письмам, из которых нужно только последнее
    (новый код входа делает старый бесполезным). Пока письма ждут квоту, старое письмо
    узнаёт о новом и снимается. Память пода: после перезапуска старое письмо может уйти,
    если новое ещё не попалось воркеру.
    """

    def __init__(self) -> None:
        self._seen: dict[str, SeenLetter] = {}

    def is_superseded(self, letter: Letter) -> bool:
        """Запоминает письмо и отвечает, есть ли с тем же ключом более новое."""
        if letter.collapse_key is None or letter.created_at is None:
            return False
        now = datetime.now(UTC)
        self._seen = {key: seen for key, seen in self._seen.items() if seen.expires_at > now}
        latest = self._seen.get(letter.collapse_key)
        if latest is not None and latest.created_at > letter.created_at:
            return True
        self._seen[letter.collapse_key] = SeenLetter(letter.created_at, letter.expires_at)
        return False
