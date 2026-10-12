import { chapter1Url } from './showcaseUrl'

test('Chapter 1 link uses VITE_SHOWCASE_URL with /c1/', () => {
  expect(chapter1Url('https://d111.cloudfront.net/')).toBe('https://d111.cloudfront.net/c1/')
  expect(chapter1Url('https://d111.cloudfront.net')).toBe('https://d111.cloudfront.net/c1/')
  expect(chapter1Url('')).toBe('http://localhost:8088/c1/')
  expect(chapter1Url(undefined)).toBe('http://localhost:8088/c1/')
})
