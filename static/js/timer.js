//script to have a countdown timer
let timeLeft = 60 * 10; //10 minute countdown

function updateTimer() {
    let minutes = Math.floor(timeLeft / 60);
    let seconds = timeLeft % 60;
    //getting display from current time
    let timerDisplay = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    //change the timer element to cur time
    document.getElementById('timer').textContent = timerDisplay;
    if (timeLeft > 0) {
        timeLeft--;
    } else {
        //when timer is done move to analysis page
        clearInterval(timerInterval);
        window.location.href = '/analysis'; 
    }
}

let timerInterval = setInterval(updateTimer, 1000);
