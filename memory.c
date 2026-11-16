/* memory.c - memory-bound work.
 *   memory 0 KB REPS : sequential streaming sum over KB kilobytes (prefetch/MLP friendly)
 *   memory 1 KB REPS : random pointer chase over KB kilobytes   (each load waits on the last) */
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int mode = argc > 1 ? atoi(argv[1]) : 0;
    long kb = argc > 2 ? atol(argv[2]) : 4096;
    int reps = argc > 3 ? atoi(argv[3]) : 2;
    long n = kb * 1024 / sizeof(long);
    long *arr = malloc(n * sizeof *arr);
    long sum = 0;

    if (mode == 0) {
        for (long i = 0; i < n; i++) arr[i] = i;
        for (int r = 0; r < reps; r++)
            for (long i = 0; i < n; i++) sum += arr[i];
    } else {
        /* Sattolo shuffle: one random cycle through every element */
        for (long i = 0; i < n; i++) arr[i] = i;
        srand(7);
        for (long i = n - 1; i > 0; i--) {
            long j = rand() % i, t = arr[i];
            arr[i] = arr[j]; arr[j] = t;
        }
        long p = 0;
        for (int r = 0; r < reps; r++)
            for (long i = 0; i < n; i++) { p = arr[p]; sum += p; }
    }
    printf("memory mode=%d kb=%ld sum=%ld\n", mode, kb, sum);
    free(arr);
    return 0;
}
