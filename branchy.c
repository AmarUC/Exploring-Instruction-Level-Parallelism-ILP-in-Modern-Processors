/* branchy.c - data-dependent branches.
 *   branchy 0 N REPS : threshold test on SORTED data   (branch is predictable)
 *   branchy 1 N REPS : threshold test on RANDOM data   (branch is a coin flip)
 * Identical instructions; only the branch pattern changes. */
#include <stdio.h>
#include <stdlib.h>

static int cmp(const void *a, const void *b) { return *(const int *)a - *(const int *)b; }

int main(int argc, char **argv) {
    int mode = argc > 1 ? atoi(argv[1]) : 1;
    int n = argc > 2 ? atoi(argv[2]) : 8192;
    int reps = argc > 3 ? atoi(argv[3]) : 20;
    int *v = malloc(n * sizeof *v);
    srand(42);
    for (int i = 0; i < n; i++) v[i] = rand() % 256;
    if (mode == 0) qsort(v, n, sizeof *v, cmp);

    long sum = 0;
    for (int r = 0; r < reps; r++)
        for (int i = 0; i < n; i++)
            if (v[i] >= 128)        /* compiled as a real branch: see -fno-if-conversion in Makefile */
                sum += v[i];
            else
                sum -= 1;
    printf("branchy mode=%d n=%d sum=%ld\n", mode, n, sum);
    free(v);
    return 0;
}
