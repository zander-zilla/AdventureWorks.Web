// C2-1 showcase paths (CloudFront Functions, cloudfront-js-2.0, viewer request). Tested by tests/showcase/test_paths_function.py.
function handler(event) {
  var r = event.request, u = r.uri;
  if (u === '/c1') return { statusCode: 301, statusDescription: 'Moved Permanently', headers: { location: { value: '/c1/' } } };
  if (u === '/c2' || u === '/c2/') return { statusCode: 302, statusDescription: 'Found', headers: { location: { value: '/#/c2/story' } } };
  if (u.endsWith('/')) r.uri = u + 'index.html';
  return r;
}
