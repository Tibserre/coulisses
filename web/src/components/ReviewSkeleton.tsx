import { Skeleton } from "@astryxdesign/core/Skeleton";

/** Lines of a transcript, of uneven lengths (the shapes, not the words). */
const LINES = [
  [1, 0.92, 0.64],
  [0.38],
  [1, 0.81],
  [1, 1, 0.97, 0.45],
  [0.72],
  [1, 0.58],
];

/** A session page while it is read: the shapes of the page it will be (header, transcript,
 *  side column, player), at their sizes, so that nothing moves when the page comes. */
export function ReviewSkeleton() {
  let n = 0;
  return (
    <>
      <header
        className="cl-review__header cl-skeleton"
        aria-busy="true"
        aria-label="Chargement de la séance"
      >
        <div className="cl-review__top cl-skeleton__top">
          <Skeleton width={180} height={12} radius={1} index={n++} />
        </div>
        <div className="cl-skeleton__heading">
          <div className="cl-skeleton__title">
            <Skeleton width={340} height={24} radius={1} index={n++} />
          </div>
          <div className="cl-skeleton__meta">
            <Skeleton width={280} height={12} radius={1} index={n++} />
          </div>
        </div>
        <div className="cl-skeleton__strip">
          <div className="cl-skeleton__strip-head">
            <Skeleton width={200} height={12} radius={1} index={n++} />
          </div>
          <Skeleton height={6} radius="rounded" index={n++} />
        </div>
      </header>
      <div className="cl-review__columns cl-skeleton">
        <div className="cl-transcript">
          <div className="cl-skeleton__lines">
            {LINES.map((widths, i) => (
              <div key={i} className="cl-skeleton__turn">
                <div className="cl-skeleton__name">
                  <Skeleton
                    width={i % 3 === 1 ? 48 : 64}
                    height={10}
                    radius={1}
                    index={i}
                  />
                </div>
                <div className="cl-skeleton__text">
                  {widths.map((w, j) => (
                    <Skeleton
                      key={j}
                      width={`${w * 100}%`}
                      height={12}
                      radius={1}
                      index={i}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
        <aside className="cl-side">
          <div className="cl-skeleton__tabs">
            <Skeleton width={110} height={12} radius={1} />
            <Skeleton width={70} height={12} radius={1} />
          </div>
          <div className="cl-skeleton__text">
            <Skeleton width="60%" height={16} radius={1} index={1} />
            <Skeleton width="100%" height={12} radius={1} index={2} />
            <Skeleton width="90%" height={12} radius={1} index={3} />
            <Skeleton width="75%" height={12} radius={1} index={4} />
          </div>
        </aside>
      </div>
      <div className="cl-player cl-skeleton cl-skeleton__player">
        <Skeleton width={36} height={36} radius="rounded" />
        <Skeleton height={4} radius="rounded" />
      </div>
    </>
  );
}
