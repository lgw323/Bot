// Hasher function (for performance, defined outside the main logic)
async function sha256(str) {
    const buffer = new TextEncoder().encode(str);
    const hashBuffer = await self.crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

self.onmessage = async (event) => {
    const { type, seed, target, startNonce } = event.data;

    if (type === 'start') {
        // ❗ 수정: 전달받은 startNonce부터 시작, 없으면 0부터
        let nonce = startNonce || 0;
        
        const PROGRESS_INTERVAL = 500000; // 성능을 위해 업데이트 주기 조정

        console.log(`Worker started. Seed: ${seed}, Target: ${target}, Start Nonce: ${nonce}`);

        while (true) {
            const dataToHash = seed + nonce;
            const hashResult = await sha256(dataToHash);

            if (hashResult.startsWith(target)) {
                self.postMessage({ type: 'success', nonce: nonce, hash: hashResult });
                self.close(); // Terminate the worker on success
                return;
            }

            if (nonce % PROGRESS_INTERVAL === 0) {
                self.postMessage({ type: 'progress', nonce: nonce });
            }

            nonce++;
        }
    }
};
