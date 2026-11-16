/* intalu.c - integer ALU work.
 *   intalu 0 N : four independent accumulator chains  (lots of ILP)
 *   intalu 1 N : one serial dependence chain          (almost no ILP)
 * Same instruction mix, so the IPC difference is ILP alone. */
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int mode = argc > 1 ? atoi(argv[1]) : 0;
    long n = argc > 2 ? atol(argv[2]) : 400000;
    volatile unsigned long seed = 12345;     /* stops the compiler folding the loop */
    unsigned long a = seed, b = seed + 1, c = seed + 2, d = seed + 3;

    if (mode == 0) {
        for (long i = 0; i < n; i++) {
            a = (a ^ i) + (a << 3);
            b = (b ^ i) + (b >> 2);
            c = (c + i) ^ (c << 5);
            d = (d + i) ^ (d >> 1);
        }
    } else {
        for (long i = 0; i < n; i++) {
            a = (a ^ i) + (a << 3);
            a = (a ^ i) + (a >> 2);
            a = (a + i) ^ (a << 5);
            a = (a + i) ^ (a >> 1);
        }
    }
    printf("intalu mode=%d n=%ld result=%lu\n", mode, n, a ^ b ^ c ^ d);
    return 0;
}
