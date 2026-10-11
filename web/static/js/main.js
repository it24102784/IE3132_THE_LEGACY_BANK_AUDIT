(() => {
  const canvas = document.querySelector(".network");
  const context = canvas instanceof HTMLCanvasElement ? canvas.getContext("2d") : null;
  const reticle = document.querySelector(".cursor-reticle");
  const targetCard = document.querySelector(".target-card");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  if (context && canvas instanceof HTMLCanvasElement) {
    let width = 0;
    let height = 0;
    let particles = [];
    let animationFrame = 0;

    const resizeCanvas = () => {
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * pixelRatio);
      canvas.height = Math.round(height * pixelRatio);
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      const count = Math.min(58, Math.max(24, Math.round((width * height) / 23000)));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.19,
        vy: (Math.random() - 0.5) * 0.19
      }));
    };

    const drawNetwork = () => {
      context.clearRect(0, 0, width, height);

      particles.forEach((particle, index) => {
        if (!reduceMotion) {
          particle.x += particle.vx;
          particle.y += particle.vy;
          if (particle.x < 0 || particle.x > width) particle.vx *= -1;
          if (particle.y < 0 || particle.y > height) particle.vy *= -1;
        }

        context.beginPath();
        context.arc(particle.x, particle.y, 1, 0, Math.PI * 2);
        context.fillStyle = "rgba(123, 255, 193, 0.45)";
        context.fill();

        for (let otherIndex = index + 1; otherIndex < particles.length; otherIndex += 1) {
          const other = particles[otherIndex];
          const dx = particle.x - other.x;
          const dy = particle.y - other.y;
          const distance = Math.hypot(dx, dy);
          if (distance < 135) {
            context.beginPath();
            context.moveTo(particle.x, particle.y);
            context.lineTo(other.x, other.y);
            context.strokeStyle = `rgba(92, 232, 236, ${0.14 * (1 - distance / 135)})`;
            context.lineWidth = 0.7;
            context.stroke();
          }
        }
      });

      if (!reduceMotion && !document.hidden) {
        animationFrame = window.requestAnimationFrame(drawNetwork);
      }
    };

    resizeCanvas();
    drawNetwork();

    window.addEventListener("resize", resizeCanvas);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        window.cancelAnimationFrame(animationFrame);
      } else if (!reduceMotion) {
        drawNetwork();
      }
    });
  }

  if (finePointer && reticle instanceof HTMLElement && targetCard instanceof HTMLElement) {
    document.addEventListener("pointermove", (event) => {
      document.documentElement.style.setProperty("--pointer-x", `${event.clientX}px`);
      document.documentElement.style.setProperty("--pointer-y", `${event.clientY}px`);
      reticle.style.left = `${event.clientX}px`;
      reticle.style.top = `${event.clientY}px`;

      const bounds = targetCard.getBoundingClientRect();
      const overTarget = event.clientX >= bounds.left
        && event.clientX <= bounds.right
        && event.clientY >= bounds.top
        && event.clientY <= bounds.bottom;

      reticle.classList.toggle("is-over-target", overTarget);
      targetCard.classList.toggle("is-targeted", overTarget);

      if (overTarget) {
        const horizontal = (event.clientX - bounds.left) / bounds.width - 0.5;
        const vertical = (event.clientY - bounds.top) / bounds.height - 0.5;
        targetCard.style.setProperty("--card-rotate-y", `${horizontal * 5}deg`);
        targetCard.style.setProperty("--card-rotate-x", `${vertical * -5}deg`);
      } else {
        targetCard.style.setProperty("--card-rotate-y", "0deg");
        targetCard.style.setProperty("--card-rotate-x", "0deg");
      }
    });
  }
})();