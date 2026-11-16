/* fpu.c - floating-point work: repeated DAXPY (y = a*x + y) plus a dot product.
 *   fpu N REPS */
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 4096;
    int reps = argc > 2 ? atoi(argv[2]) : 60;
    double *x = malloc(n * sizeof *x), *y = malloc(n * sizeof *y);
    for (int i = 0; i < n; i++) { x[i] = i * 0.5; y[i] = 1.0 / (i + 1); }

    double a = 1.0001, dot = 0.0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < n; i++) y[i] = a * x[i] + y[i];
        for (int i = 0; i < n; i++) dot += x[i] * y[i];
    }
    printf("fpu n=%d reps=%d dot=%g\n", n, reps, dot);
    free(x); free(y);
    return 0;
}
