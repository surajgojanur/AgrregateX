// Pencil reference sketches for the landing demos (fictional, AI-generated).
// The landing page shows the closest sketch to the profile instead of drawing a face,
// matched on the traits these sketches actually vary in.
const SKETCHES = [
  { id: 's02', facial_hair: 'none', eyewear: 'none', hair_style: 'straight', hair_length: 'short', scar: true },
  { id: 's03', facial_hair: 'stubble', eyewear: 'none', hair_style: 'straight', hair_length: 'short', scar: true },
  { id: 's06', facial_hair: 'stubble', eyewear: 'none', hair_style: 'wavy', hair_length: 'short', scar: true },
  { id: 's04', facial_hair: 'none', eyewear: 'none', hair_style: 'straight', hair_length: 'short', scar: false },
  { id: 's01', facial_hair: 'none', eyewear: 'none', hair_style: 'curly', hair_length: 'short', scar: false },
  { id: 's13', facial_hair: 'none', eyewear: 'none', hair_style: 'wavy', hair_length: 'short', scar: false },
  { id: 's12', facial_hair: 'stubble', eyewear: 'none', hair_style: 'wavy', hair_length: 'short', scar: false },
  { id: 's09', facial_hair: 'stubble', eyewear: 'none', hair_style: 'wavy', hair_length: 'medium', scar: false },
  { id: 's08', facial_hair: 'none', eyewear: 'glasses', hair_style: 'curly', hair_length: 'short', scar: false },
  { id: 's07', facial_hair: 'full_beard', eyewear: 'none', hair_style: 'curly', hair_length: 'medium', scar: false },
  { id: 's10', facial_hair: 'full_beard', eyewear: 'none', hair_style: 'curly', hair_length: 'long', scar: false },
  { id: 's11', facial_hair: 'full_beard', eyewear: 'none', hair_style: 'curly', hair_length: 'long', scar: false },
].map((s) => ({ ...s, url: `/landing/sketches/${s.id}.webp` }))

// Nearest available look for values the set has no sketch of.
const NEAREST = {
  facial_hair: { mustache: 'stubble', goatee: 'stubble' },
  eyewear: { round_glasses: 'glasses', rectangular_glasses: 'glasses', sunglasses: 'glasses' },
  hair_style: { spiky: 'straight', slicked_back: 'straight', side_part: 'straight' },
  hair_length: { bald: 'short', shaved: 'short' },
}
const WEIGHTS = { facial_hair: 4, eyewear: 4, hair_style: 2, hair_length: 1 }

/** The reference sketch that best matches a profile's facial hair, eyewear, hair and scars. */
export function matchSketch(profile) {
  const want = {}
  for (const key of Object.keys(WEIGHTS)) {
    const v = profile?.traits?.[key]?.value
    if (v) want[key] = NEAREST[key][v] || v
  }
  const scar = profile?.marks?.some((m) => m.type === 'scar')
  let best = SKETCHES[0]
  let bestScore = -Infinity
  for (const s of SKETCHES) {
    let score = scar === s.scar ? 2 : 0
    for (const [key, v] of Object.entries(want)) score += v === s[key] ? WEIGHTS[key] : -WEIGHTS[key]
    if (score > bestScore) [best, bestScore] = [s, score]
  }
  return best
}
