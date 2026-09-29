"""Synthetic snippets exercise masking only; these are NOT adapter fixtures."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts' / 'capture_http_fixture.py'
spec = importlib.util.spec_from_file_location('capture_http_fixture', SCRIPT)
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


@pytest.mark.parametrize('source,selector', [
    ('naver_blog', 'nick'), ('naver_cafe', 'comment_nickname'),
    ('clien', 'nickname'), ('ppomppu', 'list_name'),
])
def test_source_html_masks_identity_preserves_structure(source, selector):
    raw = (f'<div class="{selector}" data-member-id="alice77">홍길동</div>'
           '<p>본문 test.person@example.com</p>'
           '<img class="profile" src="https://cdn.test/alice.png" alt="홍길동">'
           '<a href="https://example.test/member?memberId=alice77&amp;no=17">홍길동</a>')
    masked = capture.mask_html(source, raw)
    for private in ('홍길동', 'alice77', 'test.person@example.com', 'https://cdn.test/alice.png'):
        assert private not in masked
    assert f'class="{selector}"' in masked
    assert 'data-member-id="user_a"' in masked
    assert '사용자A' in masked
    assert '<p>본문 user_a@example.invalid</p>' in masked
    assert 'no=17' in masked


def test_naver_blog_api_and_mobile_urls_share_mapping():
    masker = capture.Masker()
    listing = {'items': [{'bloggername': '블로거', 'bloggerlink': 'https://blog.naver.com/private_blog',
                          'link': 'https://blog.naver.com/private_blog/12345'}]}
    capture.mask_json('naver_blog', listing, masker)
    page = '<span class="nick">블로거</span><script>{"blogId":"private_blog"}</script>'
    masked = capture.mask_html('naver_blog', page, masker)
    result = capture.mask_json('naver_blog', listing, masker)
    assert result['items'][0]['link'] == 'https://blog.naver.com/user_a/12345'
    assert '"blogId":"user_a"' in masked
    assert 'private_blog' not in masked


def test_cafe_json_hydration_and_escaped_names():
    raw = '<script>{"memberId":"member99","nickname":"\\ud64d\\uae38\\ub3d9"}</script>'
    masked = capture.mask_html('naver_cafe', raw)
    data = json.loads(masked.removeprefix('<script>').removesuffix('</script>'))
    assert data == {'memberId': 'user_a', 'nickname': '사용자A'}


def test_youtube_comments_keep_thread_ids_and_trim_large_fields():
    original = {'id': 'video17', 'channel': '채널주인', 'channel_id': 'UCprivate',
                'channel_url': 'https://www.youtube.com/channel/UCprivate',
                'formats': [1], 'thumbnails': [2], 'automatic_captions': {'ko': []},
                'comments': [{'id': 'comment42', 'parent': 'root', 'author': '댓글사람',
                              'author_id': '@privatehandle',
                              'author_url': 'https://www.youtube.com/@privatehandle',
                              'author_thumbnail': 'https://yt3.ggpht.com/private/photo',
                              'text': '안녕 hello@example.com', 'http_headers': {'x': 'private'}}]}
    result = capture.mask_json('youtube', capture.trim_youtube(original))
    assert result['id'] == 'video17'
    assert result['comments'][0]['id'] == 'comment42'
    assert result['comments'][0]['parent'] == 'root'
    assert result['comments'][0]['author'].startswith('사용자')
    assert not capture.TRIM_KEYS.intersection(result)
    assert 'http_headers' not in result['comments'][0]
    serialized = json.dumps(result)
    assert 'private' not in serialized
    assert 'hello@example.com' not in serialized


def test_ppomppu_onclick_and_image_nickname():
    raw = ('<span class="list_name"><img src="https://cdn.test/nick.gif" alt="닉네임"></span>'
           '<a onclick="showMemberInfo(\'secretid\', \'닉네임\')">보기</a>')
    result = capture.mask_html('ppomppu', raw)
    assert 'secretid' not in result and '닉네임' not in result
    assert 'https://cdn.test/nick.gif' not in result
    assert 'showMemberInfo' in result


def test_manifest_strips_secrets_masks_urls_and_records_counts(tmp_path, capsys):
    masker = capture.Masker(['NEVER_PRINT_KEY'])
    manifest = {'keyword': '에어컨', 'captured_at': '2026-09-29T00:00:00Z',
                'requests': [{'url': 'https://name:password@blog.naver.com/private_blog/17?token=TOKEN&no=17',
                              'status_code': 200, 'encoding': 'utf-8'}],
                'notes': ['NEVER_PRINT_KEY'], 'api_key': 'NEVER_PRINT_KEY'}
    capture.write_manifest(tmp_path, manifest, masker)
    raw = (tmp_path / 'manifest.json').read_text()
    data = json.loads(raw)
    assert data['keyword'] == '에어컨'
    assert data['requests'][0]['url'] == 'https://blog.naver.com/user_a/17?no=17'
    assert data['requests'][0]['status_code'] == 200
    assert data['requests'][0]['encoding'] == 'utf-8'
    assert data['masking_stats']['id'] == 1
    for value in ('NEVER_PRINT_KEY', 'TOKEN', 'password', 'private_blog'):
        assert value not in raw
    assert not capsys.readouterr().out
    with pytest.raises(FileExistsError):
        capture.write_manifest(tmp_path, manifest, masker)
    capture.write_manifest(tmp_path, manifest, masker, force=True)


def test_whole_capture_discovers_late_identity_before_writing(tmp_path, capsys):
    recorder = capture.Recorder('clien', '검색', tmp_path)
    recorder.pending = [('list.html', '<p>나중닉네임</p>', 'utf-8'),
                        ('detail-1.html', '<span class="nickname">나중닉네임</span>', 'utf-8')]
    recorder.save()
    assert (tmp_path / 'clien/list.html').read_text() == '<p>사용자A</p>'
    assert '나중닉네임' not in capsys.readouterr().out
    with pytest.raises(FileExistsError):
        capture.Recorder('clien', '검색', tmp_path)


def test_euc_kr_preserves_unmasked_bytes(tmp_path):
    raw = '<html>\r\n<span class="list_name">홍길동</span>\r\n<p>에어컨 본문</p></html>'.encode('euc-kr')
    recorder = capture.Recorder('ppomppu', '에어컨', tmp_path)
    recorder.pending = [('detail-1.html', raw.decode('euc-kr'), 'euc-kr')]
    recorder.record('https://www.ppomppu.co.kr/zboard/view.php?id=freeboard&no=17', 200, 'euc-kr', 'detail-1.html')
    recorder.save()
    saved = (tmp_path / 'ppomppu/detail-1.html').read_bytes()
    assert saved == raw.replace('홍길동'.encode('euc-kr'), '사용자A'.encode('euc-kr'))
    assert json.loads((tmp_path / 'ppomppu/manifest.json').read_text())['requests'][0]['encoding'] == 'euc-kr'


@pytest.mark.parametrize('status', [403, 429])
def test_blocked_http_records_status_and_stops(tmp_path, monkeypatch, status):
    recorder = capture.Recorder('clien', '에어컨', tmp_path)
    monkeypatch.setattr(capture.time, 'sleep', lambda _: None)
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(status, text='blocked')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(capture.Blocked):
            recorder.get(client, 'https://www.clien.net/service/search', 'list.html')
        with pytest.raises(capture.Blocked):
            recorder.get(client, 'https://www.clien.net/service/search', 'list.html')
    assert len(requests) == 1
    assert recorder.manifest['requests'][0]['status_code'] == status
    assert not recorder.pending


def test_redirect_throttled_and_credentials_not_forwarded(tmp_path, monkeypatch):
    recorder = capture.Recorder('naver_blog', '에어컨', tmp_path)
    monkeypatch.setattr(capture.time, 'monotonic', lambda: 10)
    waits = []
    monkeypatch.setattr(capture.time, 'sleep', waits.append)
    requests = []
    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(302, headers={'Location': 'https://other.test/list'})
        return httpx.Response(200, json={'items': []})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        recorder.get(client, 'https://openapi.naver.com/list', 'list-1.json', {'X-Naver-Client-Secret': 'secret'})
    assert waits == [0, 1]
    assert 'X-Naver-Client-Secret' not in requests[1].headers
    assert [r['status_code'] for r in recorder.manifest['requests']] == [302, 200]


@pytest.mark.parametrize('source,url,expected', [
    ('naver_blog', 'https://blog.naver.com/PostView.naver?blogId=abc&logNo=17', 'https://m.blog.naver.com/abc/17'),
    ('naver_blog', 'https://blog.naver.com/abc/17', 'https://m.blog.naver.com/abc/17'),
    ('naver_cafe', 'https://cafe.naver.com/cafename/17', 'https://m.cafe.naver.com/cafename/17'),
])
def test_mobile_url(source, url, expected):
    assert capture.mobile_url(source, url) == expected


def test_article_links_and_restrictions():
    assert capture.article_urls('clien', '<a href="/service/board/park/123">글</a><a href="/login">로그인</a>',
                                'https://www.clien.net/service/search') == ['https://www.clien.net/service/board/park/123']
    assert capture.article_urls('ppomppu', '<a href="/zboard/view.php?id=freeboard&amp;no=17">글</a>',
                                'https://www.ppomppu.co.kr/search_bbs.php') == ['https://www.ppomppu.co.kr/zboard/view.php?id=freeboard&no=17']
    assert capture.restriction('로그인 후 읽기')['login']
    assert capture.restriction('등급 이상 멤버만')['grade_restricted']
    assert capture.restriction('공개 본문')['access'] == 'unknown'


def test_naver_explicit_details_without_keys(tmp_path, monkeypatch):
    monkeypatch.delenv('NAVER_CLIENT_ID', raising=False)
    monkeypatch.delenv('NAVER_CLIENT_SECRET', raising=False)
    recorder = capture.Recorder('naver_blog', '에어컨', tmp_path)
    calls = []
    monkeypatch.setattr(recorder, 'get', lambda client, url, file: calls.append((url, file)))
    capture.capture_http(recorder, SimpleNamespace(source='naver_blog', keyword='에어컨', details=1,
                                                  url=['https://blog.naver.com/private/17'], render=False))
    assert calls == [('https://m.blog.naver.com/private/17', 'detail-1.html')]
    assert 'List skipped' in recorder.manifest['notes'][0]


def test_short_member_id_does_not_corrupt_markup_or_unrelated_words():
    raw = '<span class="nickname" data-member-id=a>별명</span><p>camera</p><a href="https://blog.naver.com/a/17">글</a>'
    result = capture.mask_html('naver_blog', raw)
    assert '<span class="nickname" data-member-id=user_a>' in result
    assert '<p>camera</p><a href="https://blog.naver.com/user_a/17">' in result


def test_query_secrets_removed_without_reencoding_euc_kr():
    url = 'https://www.ppomppu.co.kr/search_bbs.php?keyword=%BF%A1%BE%EE%C4%C1&api_key=secret&start=1'
    assert capture.strip_query_secrets(url) == url.replace('&api_key=secret', '')
    assert capture.strip_query_secrets('https://example.test/?no=17&amp;token=secret&amp;x=1') == 'https://example.test/?no=17&amp;x=1'


def test_distinct_names_stable_and_json_keys_preserved():
    result = capture.mask_json('youtube', {'comments': [
        {'author': 'author', 'text': 'first'}, {'author': '다른이', 'text': 'second'},
        {'author': 'author', 'text': 'third'}]})
    assert [r['author'] for r in result['comments']] == ['사용자A', '사용자B', '사용자A']


def test_private_values_never_appear_in_error_stdout_or_saved_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv('NAVER_CLIENT_SECRET', 'SUPER_PRIVATE_SECRET')
    def fail(recorder, args):
        print('SUPER_PRIVATE_SECRET')
        raise RuntimeError('SUPER_PRIVATE_SECRET')
    monkeypatch.setattr(capture, 'capture_http', fail)
    assert capture.main(['naver_blog', '에어컨', '--out', str(tmp_path)]) == 1
    assert 'SUPER_PRIVATE_SECRET' not in str(capsys.readouterr())
    assert 'SUPER_PRIVATE_SECRET' not in (tmp_path / 'naver_blog/manifest.json').read_text()


def test_ppomppu_scoped_comments_and_authors():
    comment = {'name': '<b><a onclick="view_info(\'member77\')">별명</a></b>',
               'image': '<img src="/profiles/member77.png">',
               'meta': {'ip_display': '123.45.*.67'},
               'sub_cmt': [{'name': '<b>답글별명</b>', 'meta': {'ip_display': '99.*.1.2'}}]}
    raw = '<script>var initialCommentData = ' + json.dumps({'comments': [comment]}) + ';</script>'
    result = capture.mask_html('ppomppu', raw)
    obj = json.loads(result.split(' = ', 1)[1].split(';</script>')[0])
    assert '<b><a onclick=' in obj['comments'][0]['name']
    for private in ('별명', 'member77', '123.45.*.67', '99.*.1.2', '/profiles/'):
        assert private not in json.dumps(obj, ensure_ascii=False)
    assert capture.mask_html('ppomppu', '<script>{"name":"제품명"}</script>') == '<script>{"name":"제품명"}</script>'


def test_ppomppu_post_and_search_writer():
    raw = ('<span class="bname"><a>게시판</a></span>'
           '<li class="topTitle-name"><strong>작성자</strong>'
           '<a class="baseList-name" onclick="view_info(\'member77\')">별명</a><small>정보</small></li>'
           '<div class="content"><p class="desc"><span>게시판</span><span>검색작성자</span>'
           '<span>2026-01-01</span></p></div>'
           '<a href="/zboard/view_info.php?id=member77">보기</a>')
    result = capture.mask_html('ppomppu', raw)
    assert '별명' not in result and '검색작성자' not in result and 'member77' not in result
    assert '게시판' in result and '작성자</strong>' in result and '2026-01-01' in result


def test_clien_canonical_article_deduplication():
    raw = ''.join(f'<a href="/service/board/park/{path}">글</a>'
                  for path in ('123?x=1', '123?x=2#reply', '456', '456#reply', '789'))
    urls = capture.article_urls('clien', raw, 'https://www.clien.net/service/search')
    assert len(urls) == 3
    assert [capture.urlsplit(url).path for url in urls] == [
        '/service/board/park/123', '/service/board/park/456', '/service/board/park/789']


def test_audit_saved_synthetic_fixtures_and_cli(tmp_path, capsys):
    directory = tmp_path / 'ppomppu'
    directory.mkdir()
    raw = '<a class="baseList-name">별명</a><script>var initialCommentData = {"comments":[{"name":"댓글별명","meta":{"ip_display":"123.*.4.5"}}]};</script>'
    (directory / 'list.html').write_bytes(raw.encode('euc-kr'))
    assert sum(capture.audit_fixture(directory).values()) > 0
    assert capture.main(['--audit', str(directory)]) == 1
    assert '별명' not in capsys.readouterr().out
    (directory / 'list.html').write_bytes(capture.mask_html('ppomppu', raw).encode('euc-kr'))
    assert not capture.audit_fixture(directory)
    assert capture.main(['--audit', str(directory)]) == 0


def test_audit_youtube_urls_and_clien_attributes(tmp_path):
    for source, filename, raw in [
        ('youtube', 'list.json', json.dumps({'uploader_url': 'https://www.youtube.com/@hidden',
             'channel_url': 'https://www.youtube.com/channel/hidden', 'comments': [
                 {'author_url': 'https://other.test/person', 'author_thumbnail': 'https://cdn.test/photo'}]})),
        ('clien', 'list.html', '<span class="nickname" data-nick-id="hidden">별명</span>')]:
        directory = tmp_path / source
        directory.mkdir()
        path = directory / filename
        path.write_text(raw)
        assert capture.audit_fixture(directory)
        masked = (json.dumps(capture.mask_json(source, json.loads(raw))) if filename.endswith('.json')
                  else capture.mask_html(source, raw))
        path.write_text(masked)
        assert not capture.audit_fixture(directory)


def test_audit_placeholder_urls_and_fail_closed(tmp_path):
    directory = tmp_path / 'youtube'
    directory.mkdir()
    path = directory / 'list.json'
    path.write_text(json.dumps({'comments': [
        {'author_url': 'https://www.youtube.com/사용자A'},
        {'author_url': 'https://www.youtube.com/@%EC%82%AC%EC%9A%A9%EC%9E%90B'},
        {'author_url': 'https://www.youtube.com/user_a'}]}))
    assert capture.audit_fixture(directory) == {}
    path.write_text('invalid JSON')
    assert capture.audit_fixture(directory) == {'error': 1}
    path.unlink()
    assert capture.audit_fixture(directory) == {'error': 1}


def test_ppomppu_distinct_query_articles_remain_distinct():
    raw = ''.join(f'<a href="/zboard/view.php?id=freeboard&amp;no={n}">글</a>' for n in (17, 18))
    assert len(capture.article_urls('ppomppu', raw, 'https://www.ppomppu.co.kr/')) == 2


@pytest.mark.parametrize('declaration', [
    '<meta charset="euc-kr">',
    '<meta http-equiv="Content-Type" content="text/html; charset=EUC-KR">',
])
def test_ppomppu_declared_charset_masks_decoded_authors(tmp_path, declaration):
    raw = (declaration + '<div class="content"><p class="desc">'
           '<span>합성게시판</span><span>가상검색작성자</span><span>2026-01-01</span>'
           '</p></div><li class="topTitle-name"><a class="baseList-name">'
           '<i class="icon"></i>가상본문작성자</a></li>')
    recorder = capture.Recorder('ppomppu', '검색', tmp_path)
    recorder.pending = [('list.html', raw.encode('euc-kr').decode('euc-kr'), 'euc-kr')]
    recorder.save()
    saved = (tmp_path / 'ppomppu/list.html').read_bytes().decode('euc-kr')
    assert '가상검색작성자' not in saved
    assert '가상본문작성자' not in saved
    assert declaration in saved
    assert '합성게시판' in saved
    assert not capture.audit_fixture(tmp_path / 'ppomppu')


def test_ppomppu_declared_charset_audit_accepts_author_placeholders(tmp_path):
    directory = tmp_path / 'ppomppu'
    directory.mkdir()
    raw = ('<meta charset="euc-kr"><div class="content"><p class="desc">'
           '<span>합성게시판</span><span>사용자A</span></p></div>'
           '<li class="topTitle-name"><a class="baseList-name">'
           '<i class="icon"></i>사용자B</a></li>')
    path = directory / 'list.html'
    path.write_bytes(raw.encode('euc-kr'))
    assert capture.audit_fixture(directory) == {}
    path.write_bytes(raw.replace('사용자A', '가상검색작성자').encode('euc-kr'))
    assert capture.audit_fixture(directory) == {'name': 1}
