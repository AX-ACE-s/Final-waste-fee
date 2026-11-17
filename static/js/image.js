// 휴대폰 사진은 5MB를 넘는 경우가 많아, 보내기 전에 브라우저에서 줄인다.
// 긴 변을 1600px 이하로 맞추고 JPEG로 바꾼다 (품목을 알아보기에는 충분한 크기).
const MAX_SIDE = 1600;
const JPEG_QUALITY = 0.85;

export async function prepareImage(file) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error('이 파일은 사진으로 읽을 수 없어요. 다른 사진을 골라 주세요.');
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY));
  if (!blob) throw new Error('사진을 준비하지 못했어요. 다른 사진을 골라 주세요.');
  return blob;
}
