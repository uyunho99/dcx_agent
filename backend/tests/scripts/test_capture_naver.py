"""Offline synthetic Naver capture regressions; no host captures."""
import json
from types import SimpleNamespace

import httpx
import pytest
from test_capture_masking import capture


@pytest.mark.parametrize('source,host', [('naver_blog', 'blog'), ('naver_cafe', 'cafe')])
def test_search_extracts_ordered_canonical_articles(source, host):
    raw = ''.join(f'<a href="https://{host}.naver.com/{path}">글</a>' for path in
                  ('owner/17?tracking=x', 'owner/17#reply', 'other/18', 'owner', 'owner/no'))
    raw += '<a href="https://evil.test/owner/19">bad</a>'
    assert capture.article_urls(source, raw, 'https://search.naver.com/search.naver') == [
        f'https://{host}.naver.com/owner/17', f'https://{host}.naver.com/other/18']


def run_capture(tmp_path, monkeypatch, source, statuses=(), details=2, pages=2, max_tries=None, urls=None):
    requests = []
    def respond(request):
        requests.append(request)
        if request.url.host == 'search.naver.com':
            start = int(request.url.params['start'])
            host = 'blog' if source == 'naver_blog' else 'cafe'
            ids = [17, 18, 19] if start == 1 else [19, 20, 21]
            return httpx.Response(200, text=''.join(
                f'<a href="https://{host}.naver.com/owner/{n}">글</a>' for n in ids))
        i = sum(r.url.host != 'search.naver.com' for r in requests) - 1
        status = statuses[i] if i < len(statuses) else 200
        if source == 'naver_cafe':
            return httpx.Response(status, json={'errorCode': '0004', 'reason': '로그인하지 않았습니다.'}
                                  if status == 401 else {'result': {'article': {'contentHtml': '<p>본문</p>'}}})
        return httpx.Response(status, text='<p>본문</p>')
    client_cls = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: client_cls(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(capture.time, 'sleep', lambda _: None)
    recorder = capture.Recorder(source, '에어컨 소음', tmp_path)
    capture.capture_http(recorder, SimpleNamespace(source=source, keyword='에어컨 소음', url=urls or [],
                          details=details, pages=pages, max_tries=max_tries))
    recorder.save()
    return recorder, requests


@pytest.mark.parametrize('source,tab', [('naver_blog', 'blog'), ('naver_cafe', 'cafe')])
def test_pagination_and_browser_headers(tmp_path, monkeypatch, source, tab):
    recorder, requests = run_capture(tmp_path, monkeypatch, source, details=1)
    assert [r.url.params['start'] for r in requests[:2]] == ['1', '31']
    assert all(r.url.params['ssc'] == f'tab.{tab}.all' for r in requests[:2])
    assert requests[0].url.params['query'] == '에어컨 소음'
    assert 'Mozilla' in requests[0].headers['User-Agent']
    assert not any('x-naver' in k for r in requests for k in r.headers)
    assert [p[0] for p in recorder.pending][:2] == ['list-1.html', 'list-2.html']
    assert requests[2].url.host == ('m.blog.naver.com' if tab == 'blog' else 'article.cafe.naver.com')


@pytest.mark.parametrize('max_tries,statuses,expected', [
    (None, [401, 200, 401, 200, 200], 4), (2, [401, 200, 200], 2),
    (None, [401] * 6, 6),
])
def test_cafe_restricted_continue_and_attempt_budget(tmp_path, monkeypatch, max_tries, statuses, expected):
    urls = [f'https://cafe.naver.com/testcafe/{n}' for n in range(100, 108)]
    recorder, requests = run_capture(tmp_path, monkeypatch, 'naver_cafe', statuses, max_tries=max_tries, urls=urls)
    articles = [r for r in requests if r.url.host == 'article.cafe.naver.com']
    assert len(articles) == expected
    assert str(articles[0].url) == 'https://article.cafe.naver.com/gw/v4/cafes/testcafe/articles/100?useCafeId=false'
    assert articles[0].headers['Referer'] == 'https://m.cafe.naver.com/'
    restricted = next(r for r in recorder.manifest['requests'] if r['status_code'] == 401)
    assert restricted['restriction']['login'] is True
    assert restricted['restriction']['access'] == 'restricted'
    assert json.loads((recorder.directory / restricted['file']).read_text())['errorCode'] == '0004'
    assert (recorder.directory / f'detail-{expected}.json').exists()


def cafe_payload():
    return {'result': {'article': {'id': 17, 'writer': {'nick': '작성별명', 'id': 'writer99',
        'memberKey': 'key99', 'imageUrl': 'https://cdn.test/private.png', 'memberLevelName': '일반회원'},
        'contentHtml': '<a class="mention" href="https://cafe.naver.com/ca-fe/cafes/1/members/mention99">멘션별명</a>'},
        'comments': {'items': [{'id': 23, 'refId': 23, 'writer': {'nick': '댓글별명', 'id': 'comment99'},
        'content': '<a href="/ca-fe/cafes/1/members/linked99">프로필별명</a>'}]}}}


def test_cafe_json_masks_writers_mentions_and_audits(tmp_path):
    directory = tmp_path / 'naver_cafe'
    directory.mkdir()
    path = directory / 'detail-1.json'
    raw = cafe_payload()
    path.write_text(json.dumps(raw, ensure_ascii=False))
    assert capture.audit_fixture(directory).get('profile', 0) > 0
    masked = capture.mask_json('naver_cafe', raw)
    saved = json.dumps(masked, ensure_ascii=False)
    for private in ('작성별명', 'writer99', 'key99', 'private.png', 'mention99', '멘션별명', '댓글별명', 'comment99', 'linked99', '프로필별명'):
        assert private not in saved
    assert masked['result']['article']['id'] == 17
    assert masked['result']['comments']['items'][0]['refId'] == 23
    assert '일반회원' in saved
    path.write_text(saved)
    assert capture.audit_fixture(directory) == {}


@pytest.mark.parametrize('source', ['naver_blog', 'naver_cafe'])
def test_search_rows_and_blog_markup_masking_and_audit(tmp_path, source):
    raw = ('<div class="detail_box"><div class="user_info"><a class="name">검색별명</a></div>'
           '<a class="title_link" href="https://blog.naver.com/hiddenblog/123">제목</a></div>'
           '<div class="sds-comps-profile"><span class="sds-comps-profile-info-name-text">새검색별명</span></div>'
           '<div class="blog-nick">본문별명</div><script>var blogId = "hiddenblog";</script>'
           '<img class="profile" src="https://cdn.test/avatar.png">')
    recorder = capture.Recorder(source, '검색', tmp_path)
    recorder.pending = [('list-1.html', raw, 'utf-8')]
    recorder.record('https://m.blog.naver.com/hiddenblog/123', 200, 'utf-8', 'list-1.html')
    directory = tmp_path / source
    directory.mkdir()
    (directory / 'detail.html').write_text(raw)
    counts = capture.audit_fixture(directory)
    assert counts.get('name', 0) >= 3
    (directory / 'detail.html').unlink()
    recorder.save()
    for path in directory.iterdir():
        saved = path.read_text()
        for private in ('검색별명', '본문별명', 'hiddenblog', 'avatar.png'):
            assert private not in saved
    assert '제목' in (directory / 'list-1.html').read_text()
    assert not capture.audit_fixture(directory)


def test_blog_script_only_identity_and_attributes(tmp_path):
    raw = '<script>var blogId = "scriptowner";</script><div data-blog-id="scriptowner">scriptowner</div>'
    masked = capture.mask_html('naver_blog', raw)
    assert 'scriptowner' not in masked
    directory = tmp_path / 'naver_blog'
    directory.mkdir()
    path = directory / 'detail-1.html'
    path.write_text('<script>var blogId = "onlyscript";</script>')
    assert capture.audit_fixture(directory).get('id') == 1
    path.write_text(capture.mask_html('naver_blog', path.read_text()))
    assert not capture.audit_fixture(directory)


@pytest.mark.parametrize('status', [403, 429])
def test_cafe_block_stops_requests(tmp_path, monkeypatch, status):
    with pytest.raises(capture.Blocked):
        run_capture(tmp_path, monkeypatch, 'naver_cafe', [status, 200])
    assert not (tmp_path / 'naver_cafe/detail-2.json').exists()


def test_cli_defaults_and_validation(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(capture, 'capture_http', lambda recorder, args: seen.append(args))
    assert capture.main(['naver_cafe', '검색', '--out', str(tmp_path)]) == 0
    assert seen[0].pages == 1 and seen[0].max_tries is None
    for flags in (['--pages', '0'], ['--max-tries', '-1'], ['--render']):
        with pytest.raises(SystemExit) as exc:
            capture.main(['naver_cafe', '검색', *flags])
        assert exc.value.code == 2


@pytest.mark.parametrize('source', ['naver_blog', 'naver_cafe'])
def test_malformed_page_urls_discover_mask_save_and_audit(tmp_path, source):
    raw = ('<p>//[::1 https://blog.naver.com/[x]/1</p>'
           '<a href="//[::1?memberId=hiddenmember">link</a>'
           '<a href="https://blog.naver.com/hiddenblog/17">article</a>'
           '<span class="nick">숨긴별명</span>'
           '<script>{"blogId":"hiddenblog","nickname":"숨긴별명"}</script>'
           '<img class="profile" src="https://[broken/profile.png">')
    masker = capture.Masker()
    masker.discover_html(source, raw)
    assert 'hiddenblog' in masker.mapping and '숨긴별명' in masker.mapping
    masked = capture.mask_html(source, raw)
    for private in ('hiddenblog', 'hiddenmember', '숨긴별명', '[broken/profile.png'):
        assert private not in masked
    directory = tmp_path / source
    directory.mkdir()
    path = directory / 'list-1.html'
    path.write_text(raw)
    counts = capture.audit_fixture(directory)
    assert 'error' not in counts and counts.get('id', 0) >= 2
    path.unlink()
    recorder = capture.Recorder(source, '검색', tmp_path)
    recorder.pending = [('list-1.html', raw, 'utf-8')]
    recorder.save()
    assert capture.audit_fixture(directory) == {}


def test_malformed_url_secret_scrubbing_and_link_extraction():
    assert capture.strip_query_secrets('//[::1?token=secret&no=17') == '//[::1?no=17'
    assert capture.strip_query_secrets('//[::1') == '//[::1'
    raw = ('<a href="//[::1">bad</a><a href="https://[broken">bad</a>'
           '<a href="https://blog.naver.com/owner/17">good</a>')
    assert capture.article_urls('naver_blog', raw, 'https://search.naver.com/search.naver') == [
        'https://blog.naver.com/owner/17']


@pytest.mark.parametrize('exists,reason', [(False, 'missing_directory'), (True, 'empty_directory')])
def test_audit_absent_input_is_explicit(tmp_path, capsys, exists, reason):
    directory = tmp_path / 'naver_blog'
    if exists:
        directory.mkdir()
    assert capture.audit_fixture(directory) == {reason: 1}
    assert capture.main(['--audit', str(directory)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output['status'] == 'not_audited'
    assert output['reason'] == reason


@pytest.mark.parametrize('source,object_key', [('naver_cafe', 'writer'), ('naver_cafe', 'author'),
                                              ('naver_blog', 'author'), ('youtube', 'writer')])
def test_generic_writer_identity_keys_mask_and_audit(tmp_path, source, object_key):
    writer = {'baMemberKey': 'private_article_key', 'legacy_member_id': 'private_member',
              'id': 'private_id', 'userId': 'private_user', 'nick': '비공개별명',
              'smallProfileImageUrl': 'https://cdn.test/private-profile.png',
              'writerImageUrl': 'https://cdn.test/private-image.png',
              'memberLevel': 3, 'memberLevelName': '일반회원',
              'memberLevelIconUrl': 'https://cdn.test/level3.png', 'isManager': False,
              'verifiedMemberId': True}
    raw = {'article': {'id': 17, object_key: writer}, 'comments': {'items': [
        {'id': 21, 'refId': 21, object_key: {'baMemberKey': 'private_comment_key'}}]}}
    directory = tmp_path / source
    directory.mkdir()
    path = directory / 'detail.json'
    path.write_text(json.dumps(raw, ensure_ascii=False))
    assert capture.audit_fixture(directory).get('id') == 5
    masked = capture.mask_json(source, raw)
    assert 'private_' not in json.dumps(masked)
    assert masked['article']['id'] == 17
    assert masked['comments']['items'][0]['id'] == 21
    for key in ('memberLevel', 'memberLevelName', 'memberLevelIconUrl', 'isManager', 'verifiedMemberId'):
        assert masked['article'][object_key][key] == writer[key]
    path.write_text(json.dumps(masked, ensure_ascii=False))
    assert capture.audit_fixture(directory) == {}


def test_cafe_audit_detects_only_remaining_ba_member_keys(tmp_path):
    directory = tmp_path / 'naver_cafe'
    directory.mkdir()
    raw = {'result': {'article': {'writer': {'nick': '사용자A', 'id': 'user_a',
            'baMemberKey': 'leftover_article'}}, 'comments': {'items': [
            {'writer': {'nick': '사용자B', 'baMemberKey': 'leftover_comment'}}]}}}
    path = directory / 'detail.json'
    path.write_text(json.dumps(raw))
    assert capture.audit_fixture(directory) == {'id': 2}
    path.write_text(json.dumps(capture.mask_json('naver_cafe', raw)))
    assert capture.audit_fixture(directory) == {}
