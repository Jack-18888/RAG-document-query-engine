from app.generation.answer_service import AnswerService, Source
from app.retrieval.retrieval_service import NO_SOURCES_MESSAGE, RetrievedChunk


def _chunk(chunk_id, doc_id="doc_1", doc_name="report.pdf", text="excerpt text", score=0.9):
    return RetrievedChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        doc_name=doc_name,
        text=text,
        score=score,
    )


class _FakeChat:
    def __init__(self):
        self.messages = []
        self.result = "The answer."

    async def chat(self, messages, sleep=None):
        self.messages = messages
        return self.result


def _answer_service(chat=None):
    return AnswerService(chat or _FakeChat())


def _source(chunk):
    return Source(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        doc_name=chunk.doc_name,
        excerpt=chunk.text,
        score=chunk.score,
    )


async def test_empty_chunks_returns_canned_message_without_llm():
    chat = _FakeChat()
    service = _answer_service(chat)

    result = await service.answer("question", [])

    assert result.answer == NO_SOURCES_MESSAGE
    assert result.sources == []
    assert chat.messages == []


async def test_answer_returns_text_and_sources():
    chat = _FakeChat()
    chat.result = "Invoices must be kept 7 years."
    service = _answer_service(chat)
    chunks = [
        _chunk("chunk_1", text="Invoices must be kept 7 years.", score=0.89),
        _chunk("chunk_2", doc_name="policy.md", text="Other policy.", score=0.7),
        _chunk("chunk_3", text="Third excerpt.", score=0.5),
    ]

    result = await service.answer("retention period?", chunks)

    assert result.answer == "Invoices must be kept 7 years."
    assert result.sources == [
        _source(chunks[0]),
        _source(chunks[1]),
        _source(chunks[2]),
    ]


async def test_prompt_includes_grounding_instruction():
    chat = _FakeChat()
    service = _answer_service(chat)
    chunks = [_chunk("chunk_1", text="Invoices kept 7 years.")]

    await service.answer("how long?", chunks)

    system_message = chat.messages[0]["content"]
    assert "ONLY" in system_message
    assert "invent" in system_message
    assert "sources" in system_message

    user_message = chat.messages[1]["content"]
    assert "Invoices kept 7 years." in user_message
    assert "how long?" in user_message


async def test_chunks_numbered_in_prompt():
    chat = _FakeChat()
    service = _answer_service(chat)
    chunks = [_chunk("c1", text="first."), _chunk("c2", text="second.")]

    await service.answer("q", chunks)

    user_message = chat.messages[1]["content"]
    assert "[1] first." in user_message
    assert "[2] second." in user_message
