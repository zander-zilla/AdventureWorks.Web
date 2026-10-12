/** C2-1: where the chapter switch's "Chapter 1 · Migration" goes: <showcase>/c1/ (frozen v1.0-migration build).
 *  VITE_SHOWCASE_URL is set at image build time from Terraform output showcase_url (scripts/aws/push-images.sh);
 *  unset = the local showcase (scripts/showcase-up.sh, :8088). */
export function chapter1Url(base: string | undefined = import.meta.env.VITE_SHOWCASE_URL) {
  const b = (base ?? '').trim() || 'http://localhost:8088/'
  return (b.endsWith('/') ? b : b + '/') + 'c1/'
}
