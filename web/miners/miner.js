document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const seedValueEl = document.getElementById('seed-value');
    const targetValueEl = document.getElementById('target-value');
    const statusMessageEl = document.getElementById('status-message');
    const timerEl = document.getElementById('timer');
    const hashRateEl = document.getElementById('hash-rate');
    const nonceValueEl = document.getElementById('nonce-value');
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const resultPanel = document.getElementById('result-panel');
    const resultNonceEl = document.getElementById('result-nonce');
    const resultHashEl = document.getElementById('result-hash');
    const copyNonceBtn = document.getElementById('copy-nonce-btn');
    const progressBar = document.getElementById('progress-bar');
    
    // Practice Quiz Elements
    const practiceStatusEl = document.getElementById('practice-status');
    const practiceQuestionEl = document.getElementById('practice-question');
    const practiceAnswerEl = document.getElementById('practice-answer');
    const practiceSubmitBtn = document.getElementById('practice-submit-btn');
    const solvedCounterEl = document.getElementById('solved-counter');

    let worker;
    let timerInterval;
    let startTime;
    let lastNonce = 0;
    let seed, target;
    
    // Practice Quiz variables
    let practiceCorrectAnswer;
    let solvedCount = 0;

    // --- Practice Quiz Logic ---
    function generatePracticeQuiz() {
        const num1 = Math.floor(Math.random() * 50) + 1;
        const num2 = Math.floor(Math.random() * 50) + 1;
        const operators = ['+', '-', '*'];
        const op = operators[Math.floor(Math.random() * operators.length)];

        const question = `${num1} ${op} ${num2}`;
        practiceCorrectAnswer = eval(question);
        practiceQuestionEl.textContent = `${question} = ?`;
        practiceAnswerEl.value = '';
    }

    function handlePracticeSubmit() {
        const userAnswer = parseInt(practiceAnswerEl.value, 10);
        if (userAnswer === practiceCorrectAnswer) {
            solvedCount++;
            solvedCounterEl.textContent = solvedCount;
            practiceStatusEl.textContent = 'CORRECT!';
            practiceStatusEl.style.color = 'var(--primary-color)';
            generatePracticeQuiz();
        } else {
            practiceStatusEl.textContent = 'INCORRECT. TRY AGAIN.';
            practiceStatusEl.style.color = 'var(--secondary-color)';
        }
        setTimeout(() => { practiceStatusEl.textContent = 'IDLE...'; practiceStatusEl.style.color = 'var(--primary-color)'; }, 1500);
    }
    
    // --- Mining Logic ---
    function initialize() {
        const params = new URLSearchParams(window.location.search);
        seed = params.get('seed');
        target = params.get('target');

        if (!seed || !target) {
            document.body.innerHTML = '<h1>오류: SEED와 TARGET 파라미터가 URL에 필요합니다.</h1>';
            return;
        }

        seedValueEl.textContent = seed;
        targetValueEl.textContent = target;
        updateStatus('STANDBY', 'var(--primary-color)');
        generatePracticeQuiz();
    }

    function startMining() {
        if (typeof(Worker) === 'undefined') {
            alert('Web Worker를 지원하지 않는 브라우저입니다.');
            return;
        }

        worker = new Worker('worker.js');
        worker.onmessage = handleWorkerMessage;
        
        worker.postMessage({ type: 'start', seed, target, startNonce: 0 });

        // ❗ 수정: 결과 패널 내용 초기화 및 숨김 로직 강화
        resultNonceEl.textContent = '';
        resultHashEl.textContent = '';
        resultPanel.style.display = 'none';

        startBtn.disabled = true;
        stopBtn.disabled = false;
        startTime = Date.now();
        lastNonce = 0;
        startTimer();
        updateStatus('MINING...', 'var(--secondary-color)');
        progressBar.style.width = '0%';
        progressBar.style.transition = 'none';
    }

    function stopMining() {
        if (worker) {
            worker.terminate();
            worker = null;
        }
        clearInterval(timerInterval);
        startBtn.disabled = false;
        stopBtn.disabled = true;
        updateStatus('TERMINATED', 'var(--primary-color)');
    }

    function handleWorkerMessage(event) {
        const { type, nonce, hash } = event.data;
        if (type === 'progress') {
            lastNonce = nonce;
            nonceValueEl.textContent = nonce.toLocaleString();
            
            const estimatedMaxNonce = Math.pow(16, target.length) * 10;
            const progress = Math.min((nonce / estimatedMaxNonce) * 100, 100);
            progressBar.style.transition = 'width 0.5s linear';
            progressBar.style.width = `${progress}%`;

        } else if (type === 'success') {
            lastNonce = nonce;
            nonceValueEl.textContent = nonce.toLocaleString();

            stopMining();
            updateStatus('SUCCESS', 'var(--primary-color)');
            resultNonceEl.textContent = nonce;
            resultHashEl.textContent = hash;
            resultPanel.style.display = 'block';
            copyNonceBtn.textContent = 'COPY_NONCE';
        }
    }
    
    function updateStatus(message, color) {
        statusMessageEl.textContent = message;
        statusMessageEl.style.color = color;
    }

    function startTimer() {
        timerInterval = setInterval(() => {
            const now = Date.now();
            const elapsedSeconds = (now - startTime) / 1000;

            const hours = Math.floor(elapsedSeconds / 3600).toString().padStart(2, '0');
            const minutes = Math.floor((elapsedSeconds % 3600) / 60).toString().padStart(2, '0');
            const seconds = (Math.floor(elapsedSeconds) % 60).toString().padStart(2, '0');
            timerEl.textContent = `${hours}:${minutes}:${seconds}`;

            // ❗ 수정: 평균 해시 속도 계산 로직으로 변경
            if (elapsedSeconds > 0) {
                const averageRate = lastNonce / elapsedSeconds;
                hashRateEl.textContent = `${Math.round(averageRate).toLocaleString()} H/s`;
            }

        }, 1000);
    }

    function copyNonceToClipboard() {
        const textArea = document.createElement("textarea");
        textArea.value = resultNonceEl.textContent;
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            copyNonceBtn.textContent = 'COPIED!';
        } catch (err) {
            console.error('클립보드 복사 실패:', err);
            copyNonceBtn.textContent = 'COPY_FAILED';
        }
        document.body.removeChild(textArea);
        setTimeout(() => copyNonceBtn.textContent = 'COPY_NONCE', 2000);
    }

    // Event Listeners
    startBtn.addEventListener('click', startMining);
    stopBtn.addEventListener('click', stopMining);
    copyNonceBtn.addEventListener('click', copyNonceToClipboard);
    practiceSubmitBtn.addEventListener('click', handlePracticeSubmit);
    practiceAnswerEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handlePracticeSubmit();
    });

    initialize();
});
