export function randomIntWithLength(length: number): number {
  if (length <= 0) throw new Error("Length must be positive");

  const min = 10 ** (length - 1);
  const max = 10 ** length - 1;

  return Math.floor(Math.random() * (max - min + 1)) + min;
}
